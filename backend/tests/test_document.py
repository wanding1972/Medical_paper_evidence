import unittest
from pydantic import ValidationError
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import Reference
from evidence_check.domains.document.api import parse_document
from support import document, policy


class DocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.policy = policy()

    def test_numeric_forms_and_anchor_offsets(self):
        for raw, expected in [('[1]',(1,)),('[1,2]',(1,2)),('[1-3]',(1,2,3)),
                              ('[1，3-4,1]',(1,3,4)),('[ 1 , 2 ]',(1,2))]:
            with self.subTest(raw=raw):
                text = '\n  Synthetic '+raw+'.'
                bundle = parse_document(document(text),self.policy)
                anchor = bundle.sentences[0].citations[0]
                self.assertEqual(anchor.reference_ids, expected)
                self.assertEqual(text[anchor.location.char_start:anchor.location.char_end],raw)
                self.assertEqual(anchor.location.paragraph_index,1)

    def test_sentence_positions_chinese_decimal_post_punctuation(self):
        text = '# Discussion\n结果为3.5。 [1]\nNext statement.[2] End!'
        bundle = parse_document(document(text),self.policy)
        self.assertEqual(len(bundle.sentences),4)
        self.assertEqual(bundle.sentences[1].citations[0].reference_ids,(1,))
        self.assertEqual(bundle.sentences[2].citations[0].reference_ids,(2,))
        for sentence in bundle.sentences:
            where=sentence.location
            self.assertEqual(text[where.char_start:where.char_end],sentence.text)

    def test_malformed_ranges_fail_before_expansion(self):
        for raw in ['[0]','[3-1]','[1-999999999]','[1,a]','[1--3]','[1','[1;2]']:
            with self.subTest(raw=raw), self.assertRaises(InputError):
                parse_document(document('Synthetic '+raw+'.'),self.policy)

    def test_reference_and_scope_admission(self):
        cases=[
            ({'authorized':False},'authorization_required'),
            ({'single_section':False},'single_section_required'),
            ({'language_mode':'fr-fr'},'unsupported_language'),
            ({'text':' '},'empty_document'),
            ({'text':'中'*5001},'document_too_long'),
            ({'text':'word '*3001},'document_too_long'),
            ({'text':'# One\ntext\n# Two\ntext'},'multiple_sections'),
            ({'references':tuple(Reference(reference_id=n,title='X') for n in range(1,32))},'too_many_references'),
            ({'references':(Reference(reference_id=0,title='X'),)},'invalid_reference_id'),
            ({'references':(Reference(reference_id=1,title=''),)},'empty_reference_title'),
            ({'references':(Reference(reference_id=1,title='A'),Reference(reference_id=1,title='B'))},'duplicate_reference'),
        ]
        for changes,code in cases:
            with self.subTest(code=code), self.assertRaises(InputError) as caught:
                parse_document(document(**changes),self.policy)
            self.assertEqual(caught.exception.code,code)

    def test_mixed_language_counts_independently(self):
        text='中'*5000+' word'*3000
        self.assertTrue(parse_document(document(text),self.policy).sentences)
        with self.assertRaises(InputError):
            parse_document(document(text+' word'),self.policy)

    def test_pii_blocks_with_no_raw_data_in_error(self):
        for text in ['患者姓名：某人','Patient name: PRIVATE_NAME']:
            with self.subTest(text=text),self.assertRaises(InputError) as caught:
                parse_document(document(text),self.policy)
            self.assertEqual(caught.exception.code,'patient_data_detected')
            self.assertNotIn(text,str(caught.exception))

    def test_strict_types_unknown_fields(self):
        with self.assertRaises(ValidationError): document(authorized=1)
        with self.assertRaises(ValidationError): document(extra_field=True)
        with self.assertRaises(ValidationError): Reference(reference_id='1',title='x')
