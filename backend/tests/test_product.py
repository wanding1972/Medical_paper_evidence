import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from evidence_check.application.product import run_audit
from evidence_check.contracts.errors import InputError, EvidenceCheckError
from evidence_check.contracts.models import ClaimCandidate
from evidence_check.contracts.product import ProductRequest, Observation, CandidateBatch, ObservationBatch
from evidence_check.domains.document.api import parse_document
from evidence_check.domains.claim.api import normalize_claims
from evidence_check.domains.evidence.api import retrieve
from evidence_check.infrastructure.api import load_product_policy
from evidence_check.infrastructure.pdf import parse_pdf
from evidence_check.infrastructure.model import StructuredModel
from support import BACKEND,document,policy


def product_policy():return load_product_policy(BACKEND/'config')


def pdf_bytes(text='Synthetic treatment reduced the observed risk in the selected sample. This is fictional test text.'):
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_textbox(pymupdf.Rect(40,40,550,700),text)
        return pdf.tobytes()


def request_with_source(text='Synthetic treatment reduced risk[1].'):
    legacy=policy();product=product_policy()
    source=parse_pdf(pdf_bytes(),1,'source-1',legacy,product)
    return ProductRequest(document=document(text),sources=(source,)),legacy,product


def observation(item,**changes):
    values=dict(claim_start=item.claim.location.char_start,evidence_ids=tuple(s.span_id for s in item.evidence),
        support_relation='supports',scope_relation='match',causal_relation='compatible',direction_relation='match',numeric_relation='match',
        rationale='Synthetic reviewer comparison, not a medical fact.',origin=product_policy().origins.human)
    return Observation(**(values|changes))


class ProductTests(unittest.TestCase):
    def test_real_pdf_page_span_and_cited_only_retrieval(self):
        request,legacy,product=request_with_source()
        report=run_audit(request,legacy,product);item=report.assessments[0]
        self.assertTrue(item.evidence)
        for span in item.evidence:
            source=request.sources[0];page=source.pages[span.page-1]
            self.assertEqual(page.text[span.start:span.end],span.text)
            self.assertEqual(span.reference_id,1)
        other=request.sources[0].model_copy(update={'reference_id':9})
        report=run_audit(request.model_copy(update={'sources':(other,)}),legacy,product)
        self.assertEqual(report.assessments[0].evidence,())

    def test_no_observation_never_becomes_supported(self):
        request,legacy,product=request_with_source()
        item=run_audit(request,legacy,product).assessments[0]
        self.assertEqual(item.predicted_label,'unverified')
        self.assertEqual(item.claim.claim_type,'effectiveness')

    def test_supported_requires_grounded_observation(self):
        request,legacy,product=request_with_source();item=run_audit(request,legacy,product).assessments[0]
        result=run_audit(request.model_copy(update={'observations':(observation(item),)}),legacy,product)
        self.assertEqual(result.assessments[0].predicted_label,'supported')
        self.assertEqual(result.assessments[0].review_status,'需复核')

    def test_all_semantic_rules_from_configuration(self):
        request,legacy,product=request_with_source();item=run_audit(request,legacy,product).assessments[0]
        cases=[({'support_relation':'partial','scope_relation':'mismatch'},'scope_mismatch','partially_supported'),
               ({'support_relation':'partial','causal_relation':'overclaim'},'causality_overclaim','partially_supported'),
               ({'support_relation':'opposes','direction_relation':'opposite'},'direction_mismatch','contradicted'),
               ({'support_relation':'opposes','numeric_relation':'mismatch'},'numeric_mismatch','contradicted')]
        for changes,rule,label in cases:
            with self.subTest(rule=rule):
                result=run_audit(request.model_copy(update={'observations':(observation(item,**changes),)}),legacy,product).assessments[0]
                self.assertIn(rule,[f.rule_id for f in result.findings]);self.assertEqual(result.predicted_label,label)

    def test_bad_observations_and_unknown_are_conservative(self):
        request,legacy,product=request_with_source();item=run_audit(request,legacy,product).assessments[0]
        for changes in [{'evidence_ids':('invented',)},{'claim_start':999},{'origin':'fake'},{'support_relation':'invented'},{'rationale':''}]:
            with self.subTest(changes=changes),self.assertRaises(InputError):
                run_audit(request.model_copy(update={'observations':(observation(item,**changes),)}),legacy,product)
        unknown=observation(item,support_relation='unknown')
        self.assertEqual(run_audit(request.model_copy(update={'observations':(unknown,)}),legacy,product).assessments[0].predicted_label,'unverified')

    def test_multisource_missing_and_conflicts_preserved(self):
        from evidence_check.contracts.models import Reference
        request,legacy,product=request_with_source('Synthetic treatment reduced risk[1,2].')
        document2=request.document.model_copy(update={'references':request.document.references+(Reference(reference_id=2,title='Second source'),)})
        request=request.model_copy(update={'document':document2});item=run_audit(request,legacy,product).assessments[0]
        partial=run_audit(request.model_copy(update={'observations':(observation(item),)}),legacy,product).assessments[0]
        self.assertEqual(partial.predicted_label,'unverified');self.assertIn('source_unavailable',[f.rule_id for f in partial.findings])
        second=parse_pdf(pdf_bytes(),2,'source-2',legacy,product)
        request=request.model_copy(update={'sources':request.sources+(second,)})
        item=run_audit(request,legacy,product).assessments[0]
        first_ids=tuple(e.span_id for e in item.evidence if e.reference_id==1);second_ids=tuple(e.span_id for e in item.evidence if e.reference_id==2)
        observations=(observation(item,evidence_ids=first_ids),observation(item,evidence_ids=second_ids,support_relation='opposes',direction_relation='opposite'))
        result=run_audit(request.model_copy(update={'observations':observations}),legacy,product).assessments[0]
        self.assertEqual(result.predicted_label,'unverified');self.assertIn('direction_mismatch',[f.rule_id for f in result.findings])

    def test_scanned_corrupt_and_missing_sources(self):
        legacy=policy();product=product_policy()
        with pymupdf.open() as pdf:
            pdf.new_page();empty=pdf.tobytes()
        self.assertEqual(parse_pdf(empty,1,'blank',legacy,product).error_code,'pdf_no_text')
        self.assertEqual(parse_pdf(b'broken',1,'broken',legacy,product).error_code,'pdf_unreadable')
        report=run_audit(ProductRequest(document=document()),legacy,product)
        self.assertEqual(report.assessments[0].predicted_label,'not_assessable')

    def test_pdf_pii_blocks_and_model_consent_before_call(self):
        legacy=policy();product=product_policy()
        with self.assertRaises(InputError):parse_pdf(pdf_bytes('Patient name: PRIVATE_NAME'),1,'private',legacy,product)
        class Fake:
            name='fake'
            def extract(self,doc):raise AssertionError('Must not be called')
        with self.assertRaises(InputError):run_audit(ProductRequest(document=document()),legacy,product,Fake())

    def test_unrelated_fulltext_no_candidate_is_unverified(self):
        request,legacy,product=request_with_source('Zebras occupy woodland habitats[1].')
        report=run_audit(request,legacy,product)
        self.assertEqual(report.assessments[0].predicted_label,'unverified')
        self.assertIn('unsupported_claim',[f.rule_id for f in report.assessments[0].findings])

    def test_structured_model_rejects_malformed_output(self):
        product=product_policy()
        env={product.model.endpoint_env:'https://model.example/v1/chat/completions',product.model.key_env:'test-only',product.model.name_env:'test-model'}
        import httpx
        with patch.dict('os.environ',env),patch('evidence_check.infrastructure.model.httpx.post') as post:
            response=httpx.Response(200,json={'choices':[{'message':{'content':'{"final_label":"supported"}'}}]},request=httpx.Request('POST',env[product.model.endpoint_env]))
            post.return_value=response
            with self.assertRaises(EvidenceCheckError):StructuredModel(product).extract(document())
        env[product.model.endpoint_env]='http://insecure.example'
        with patch.dict('os.environ',env),self.assertRaises(EvidenceCheckError):StructuredModel(product)

    def test_abstract_is_never_fine_grained_evidence(self):
        legacy=policy();product=product_policy()
        source=parse_pdf(pdf_bytes('Abstract\nSynthetic treatment reduced the observed risk in this summary.'),1,'abstract',legacy,product)
        result=run_audit(ProductRequest(document=document('Synthetic treatment reduced risk[1].'),sources=(source,)),legacy,product)
        self.assertEqual(result.assessments[0].evidence,())
        self.assertEqual(result.assessments[0].predicted_label,'not_assessable')

    def test_unknown_qualifier_does_not_upgrade_support(self):
        request,legacy,product=request_with_source();item=run_audit(request,legacy,product).assessments[0]
        reviewed=observation(item,scope_relation='unknown')
        result=run_audit(request.model_copy(update={'observations':(reviewed,)}),legacy,product)
        self.assertEqual(result.assessments[0].predicted_label,'unverified')

    def test_input_bytes_are_parsed_without_plaintext_disk(self):
        from evidence_check.infrastructure.api import read_uploaded_document
        from io import BytesIO
        from docx import Document
        text='Synthetic treatment reduced risk[1].'
        word=Document();word.add_paragraph(text);buffer=BytesIO();word.save(buffer)
        self.assertEqual(read_uploaded_document(buffer.getvalue(),'.docx',policy()),text)
        self.assertEqual(read_uploaded_document(text.encode(),'.md',policy()),text)
        with self.assertRaises(EvidenceCheckError):read_uploaded_document(b'broken','.docx',policy())

    def test_incomplete_counter_policy_is_rejected(self):
        from evidence_check.contracts.product_policy import ProductPolicy
        from pydantic import ValidationError
        data=product_policy().model_dump(mode='json');data['counters'].pop()
        with self.assertRaises(ValidationError):ProductPolicy.model_validate_json(json.dumps(data))

    def test_model_success_is_validated_and_raw_response_retained(self):
        product=product_policy()
        env={product.model.endpoint_env:'https://model.example/v1/chat/completions',product.model.key_env:'test-only',product.model.name_env:'test-model'}
        import httpx
        batch=CandidateBatch(claims=(ClaimCandidate(start=0,end=len(document().text),text=document().text),))
        with patch.dict('os.environ',env),patch('evidence_check.infrastructure.model.httpx.post') as post:
            post.return_value=httpx.Response(200,json={'choices':[{'message':{'content':batch.model_dump_json()}}]},request=httpx.Request('POST',env[product.model.endpoint_env]))
            model=StructuredModel(product)
            self.assertEqual(model.extract(document()),batch);self.assertEqual(len(model.responses),1)
            schema=post.call_args.kwargs['json']['response_format']['json_schema']['schema']
            self.assertEqual(set(schema['required']),set(schema['properties']))

    def test_pdf_and_model_deadline_propagates_as_step_failure(self):
        legacy=policy();product=product_policy()
        def expired():raise EvidenceCheckError('task_timeout','Budget exhausted.')
        with self.assertRaises(EvidenceCheckError):parse_pdf(pdf_bytes(),1,'source',legacy,product,expired)

    def test_global_model_disable_cannot_be_overridden_by_consent(self):
        request,legacy,product=request_with_source()
        class Fake:
            name='disabled-fake'
            def extract(self,doc):raise AssertionError('Disabled model was called')
        with self.assertRaises(InputError) as caught:
            run_audit(request.model_copy(update={'model_consent':True}),legacy,product,Fake())
        self.assertEqual(caught.exception.code,'model_disabled')
        from evidence_check.contracts.product_policy import ProductPolicy
        from pydantic import ValidationError
        data=product.model_dump(mode='json');data['model_gates']=[]
        with self.assertRaises(ValidationError):ProductPolicy.model_validate_json(json.dumps(data))

    def test_evidence_identity_includes_actual_source_content(self):
        request,legacy,product=request_with_source()
        first=run_audit(request,legacy,product).assessments[0]
        source=request.sources[0].model_copy(update={'sha256':'different-fulltext-hash'})
        second=run_audit(request.model_copy(update={'sources':(source,)}),legacy,product).assessments[0]
        self.assertNotEqual(first.evidence[0].span_id,second.evidence[0].span_id)
        with self.assertRaises(InputError):
            run_audit(request.model_copy(update={'sources':(source,),'observations':(observation(first),)}),legacy,product)
