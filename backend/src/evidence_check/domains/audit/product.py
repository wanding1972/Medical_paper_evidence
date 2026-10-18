"""Grounded observations and conservative configurable multi-source decisions."""
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import ClaimRecord, Finding
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.predicates import matches
from evidence_check.contracts.product import SourceDocument, EvidenceSpan, Observation, DecisionFacts, ClaimAssessment
from evidence_check.contracts.product_policy import ProductPolicy


def _validate(observations: tuple[Observation, ...], claim: ClaimRecord, evidence: tuple[EvidenceSpan, ...], policy: ProductPolicy) -> None:
    ids={span.span_id for span in evidence};seen=set()
    for observation in observations:
        key=frozenset(observation.evidence_ids)
        if observation.claim_start != claim.location.char_start or not key or not key <= ids or key in seen:
            raise InputError('invalid_observation','Comparison must point to unique, retrieved evidence of this claim.')
        if not observation.rationale.strip():raise InputError('invalid_observation','Comparison requires a review rationale.')
        if observation.origin not in (policy.origins.human,policy.origins.model):
            raise InputError('invalid_observation','Unknown comparison provenance.')
        for name in type(policy.relations).model_fields:
            if getattr(observation,name) not in getattr(policy.relations,name):raise InputError('invalid_observation','Unknown relationship vocabulary.')
        seen.add(key)


def assess(claim: ClaimRecord, references: tuple[int, ...], sources: tuple[SourceDocument, ...],
           evidence: tuple[EvidenceSpan, ...], observations: tuple[Observation, ...], legacy: Policy, policy: ProductPolicy) -> ClaimAssessment:
    _validate(observations,claim,evidence,policy)
    known=set(references)
    readable={s.reference_id for s in sources if s.error_code is None and any(not p.excluded for page in s.pages for p in page.paragraphs)}
    resolved=tuple(n for n in claim.citation_ids if n in known)
    available=tuple(n for n in resolved if n in readable)
    unresolved=tuple(n for n in claim.citation_ids if n not in known)
    unavailable=tuple(n for n in resolved if n not in readable)
    observed_ids={item for observation in observations for item in observation.evidence_ids}
    observed_sources={span.reference_id for span in evidence if span.span_id in observed_ids}
    values={counter.fact:sum(getattr(o,counter.field)==counter.value for o in observations) for counter in policy.counters}
    facts=DecisionFacts(citation_count=len(claim.citation_ids),unresolved_count=len(unresolved),
        available_count=len(available),unavailable_count=len(unavailable),evidence_count=len(evidence),
        comparison_count=len(observations),unreviewed_source_count=len(set(available)-observed_sources),**values)
    rule_map={r.id:r for r in legacy.audit.rules}
    reference_fields={'citation_ids':claim.citation_ids,'resolved_ids':resolved,'unresolved_ids':unresolved,
                      'available_ids':available,'unavailable_ids':unavailable}
    findings=[]
    for trigger in policy.rule_triggers:
        if matches(trigger.when,facts):
            rule=rule_map[trigger.rule_id]
            findings.append(Finding(rule_id=rule.id,severity=rule.severity,label=rule.label,
                location=claim.location,claim_text=claim.text,citation_ids=reference_fields[trigger.reference_field],
                message=rule.message,guidance=rule.guidance,review_status=legacy.audit.review_status))
    label=next((row.label for row in policy.decisions if matches(row.when,facts)),policy.default_label)
    return ClaimAssessment(claim=claim,evidence=evidence,observations=observations,findings=tuple(findings),
        predicted_label=label,review_status=legacy.audit.review_status,facts=facts)
