import unittest
from evidence_check.application.evaluation import evaluate
from evidence_check.contracts.errors import InputError
from support import policy
from test_product import product_policy


class EvaluationTests(unittest.TestCase):
    def fixture(self):
        gold=[{'record_id':'EN-EN-001','source_document_id':'held-out-1','claim_text':'Synthetic claim.',
            'annotation_status':'confirmed','language_mode':'en-en','final_label':'not_assessable',
            'rule_ids':['missing_citation'],'citation_ids':[]}]
        predictions=[{'record_id':'EN-EN-001','predicted_label':'not_assessable','rule_ids':['missing_citation'],'citation_ids':[]}]
        manifest={'blind_documents':['held-out-1'],'development_documents':['training-1']}
        return gold,predictions,manifest

    def test_precision_recall_and_insufficient_samples_do_not_pass(self):
        gold,predictions,manifest=self.fixture()
        result=evaluate(gold,predictions,manifest,policy(),product_policy())
        self.assertEqual(result['by_rule']['missing_citation']['precision'],1)
        self.assertEqual(result['by_rule']['missing_citation']['recall'],1)
        self.assertIsNone(result['by_rule']['scope_mismatch']['precision'])
        self.assertFalse(result['passed'])

    def test_pending_and_leaked_splits_are_rejected(self):
        gold,predictions,manifest=self.fixture();gold[0]['annotation_status']='pending'
        with self.assertRaises(InputError):evaluate(gold,predictions,manifest,policy(),product_policy())
        gold[0]['annotation_status']='confirmed';manifest['development_documents']=['held-out-1']
        with self.assertRaises(InputError):evaluate(gold,predictions,manifest,policy(),product_policy())

    def test_missing_predictions_and_no_predictions_fail(self):
        gold,predictions,manifest=self.fixture()
        with self.assertRaises(InputError):evaluate(gold,[],manifest,policy(),product_policy())
        predictions[0]['rule_ids']=[]
        result=evaluate(gold,predictions,manifest,policy(),product_policy())
        self.assertEqual(result['by_rule']['missing_citation']['fn'],1)
        self.assertIsNone(result['by_rule']['missing_citation']['precision'])
        self.assertFalse(result['precision_gates']['missing_citation'])
