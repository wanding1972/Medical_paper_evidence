"""Configured sentence candidates, not medical fact determinations."""
import re
from evidence_check.contracts.models import ClaimCandidate, DocumentBundle
from evidence_check.contracts.product_policy import ProductPolicy


def extract(bundle: DocumentBundle, policy: ProductPolicy) -> tuple[ClaimCandidate, ...]:
    candidates=[]
    for sentence in bundle.sentences:
        pattern=next((p for p in policy.candidate_patterns if re.search(p.pattern,sentence.text,re.IGNORECASE)),None)
        if pattern is not None:
            candidates.append(ClaimCandidate(start=sentence.location.char_start,end=sentence.location.char_end,text=sentence.text,
                claim_type=pattern.claim_type,assertion_strength=pattern.assertion_strength))
    return tuple(candidates)
