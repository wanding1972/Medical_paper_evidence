from hashlib import sha256
import unittest
from evidence_check.application.api import audit_document
from evidence_check.contracts.models import ClaimCandidate, Reference
from support import document, policy


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.policy=policy()

    def test_unknown_and_unverified_fulltext_record_all(self):
        report=audit_document(document('Synthetic[1,9].'),self.policy)
        self.assertEqual([(f.rule_id,f.citation_ids) for f in report.findings],
                         [('unresolved_reference',(9,)),('source_unavailable',(1,))])
        self.assertTrue(all(f.label=='not_assessable' and f.review_status=='需复核' for f in report.findings))
        self.assertEqual(report.summary.semantic_assessed_claim_count,0)
        self.assertEqual(dict(report.summary.by_rule),{'unresolved_reference':1,'source_unavailable':1})

    def test_only_explicit_claim_missing_citation(self):
        text='Synthetic uncited assertion.'
        self.assertEqual(audit_document(document(text),self.policy).findings,())
        claim=ClaimCandidate(start=0,end=len(text),text=text)
        report=audit_document(document(text,claims=(claim,)),self.policy)
        self.assertEqual([f.rule_id for f in report.findings],['missing_citation'])
        self.assertEqual(report.summary.manual_claim_count,1)

    def test_complete_reference_still_not_supported(self):
        report=audit_document(document(),self.policy)
        self.assertEqual(report.findings[0].rule_id,'source_unavailable')
        self.assertNotIn('supported',[f.label for f in report.findings])

    def test_hash_includes_complete_input(self):
        first=document()
        report=audit_document(first,self.policy)
        self.assertEqual(report.input_sha256,sha256(first.model_dump_json().encode()).hexdigest())
        changed=document(references=(Reference(reference_id=1,title='Different source'),))
        self.assertNotEqual(report.input_sha256,audit_document(changed,self.policy).input_sha256)

    def test_no_reference_no_claim_not_an_evidence_verdict(self):
        report=audit_document(document('Transition sentence.',references=()),self.policy)
        self.assertEqual(report.findings,())
        self.assertIn('未进行',report.audit_scope)
