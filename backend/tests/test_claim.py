import unittest
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import ClaimCandidate
from evidence_check.domains.document.api import parse_document
from evidence_check.domains.claim.api import normalize_claims
from support import document, policy


class ClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.policy=policy()

    def test_valid_verbatim_candidate(self):
        text='First[1]. Next.'
        candidate=ClaimCandidate(start=0,end=9,text=text[:9])
        records=normalize_claims(parse_document(document(text),self.policy),(candidate,),self.policy)
        self.assertEqual(records[0].citation_ids,(1,))
        self.assertEqual(records[0].location.char_end,9)

    def test_invalid_candidate_main_paths(self):
        text='First[1]. Next.'
        candidates=[
            ClaimCandidate(start=-1,end=5,text='First'),
            ClaimCandidate(start=0,end=999,text=text),
            ClaimCandidate(start=5,end=2,text=''),
            ClaimCandidate(start=0,end=5,text='WRONG'),
            ClaimCandidate(start=0,end=len(text),text=text),
            ClaimCandidate(start=0,end=5,text='First'),
        ]
        bundle=parse_document(document(text),self.policy)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(InputError):
                normalize_claims(bundle,(candidate,),self.policy)

    def test_overlap_and_exact_end_boundary(self):
        text='A selected claim.'
        candidate=ClaimCandidate(start=0,end=len(text),text=text)
        bundle=parse_document(document(text),self.policy)
        self.assertEqual(len(normalize_claims(bundle,(candidate,),self.policy)),1)
        with self.assertRaises(InputError) as caught:
            normalize_claims(bundle,(candidate,candidate),self.policy)
        self.assertEqual(caught.exception.code,'overlapping_claims')
