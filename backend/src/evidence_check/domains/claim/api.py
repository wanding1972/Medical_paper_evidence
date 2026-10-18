"""Public candidate validation; never invent or infer a medical Claim."""
from evidence_check.contracts.models import ClaimCandidate, ClaimFacts, ClaimRecord, DocumentBundle
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.predicates import enforce


def normalize_claims(bundle: DocumentBundle, candidates: tuple[ClaimCandidate, ...], policy: Policy) -> tuple[ClaimRecord, ...]:
    records = []
    for index, candidate in enumerate(candidates):
        containing = tuple(sentence for sentence in bundle.sentences
            if sentence.location.char_start <= candidate.start < candidate.end <= sentence.location.char_end)
        anchors = tuple(anchor for sentence in containing for anchor in sentence.citations)
        omitted = sum(not (candidate.start <= anchor.location.char_start
                           and anchor.location.char_end <= candidate.end) for anchor in anchors)
        overlaps = sum(candidate.start < other.end and other.start < candidate.end for other in candidates[:index])
        facts = ClaimFacts(start=candidate.start, end_overflow=candidate.end - len(bundle.text),
            span_length=candidate.end - candidate.start,
            text_matches=bundle.text[candidate.start:candidate.end] == candidate.text,
            containing_sentence_count=len(containing), omitted_citation_count=omitted, overlap_count=overlaps)
        enforce(policy.limits.claim_gates, facts)
        sentence = containing[0]
        location = sentence.location.model_copy(update={"char_start":candidate.start,"char_end":candidate.end})
        records.append(ClaimRecord(text=candidate.text, location=location,
            claim_type=candidate.claim_type,assertion_strength=candidate.assertion_strength,qualifiers=candidate.qualifiers,
            citation_ids=tuple(dict.fromkeys(n for anchor in anchors for n in anchor.reference_ids))))
    return tuple(records)


def extract_candidates(bundle: DocumentBundle, policy):
    from evidence_check.domains.claim.candidates import extract
    return extract(bundle, policy)
