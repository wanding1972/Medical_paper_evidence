"""Pure configuration execution; no rule IDs, labels or severities in code."""
from evidence_check.contracts.models import AuditFacts, ClaimRecord, DocumentBundle, Finding, Sentence
from evidence_check.contracts.policy import Policy, Rule
from evidence_check.contracts.predicates import matches


def _facts(unit: Sentence | ClaimRecord, known: set[int]) -> AuditFacts:
    ids = unit.citation_ids if isinstance(unit, ClaimRecord) else tuple(
        dict.fromkeys(n for anchor in unit.citations for n in anchor.reference_ids))
    unresolved = tuple(n for n in ids if n not in known)
    resolved = tuple(n for n in ids if n in known)
    return AuditFacts(citation_ids=ids, unresolved_ids=unresolved, resolved_ids=resolved,
        citation_count=len(ids), unresolved_count=len(unresolved), resolved_count=len(resolved))


def _finding(rule: Rule, unit: Sentence | ClaimRecord, facts: AuditFacts, policy: Policy) -> Finding:
    return Finding(rule_id=rule.id, severity=rule.severity, label=rule.label,
        location=unit.location, claim_text=unit.text,
        citation_ids=getattr(facts, rule.reference_field), message=rule.message,
        guidance=rule.guidance, review_status=policy.audit.review_status)


def evaluate(bundle: DocumentBundle, claims: tuple[ClaimRecord, ...], policy: Policy) -> tuple[Finding, ...]:
    known = {reference.reference_id for reference in bundle.references}
    collections = {"sentence":bundle.sentences, "claim":claims}
    findings = []
    for rule in policy.audit.rules:
        if not rule.enabled:
            continue
        for unit in collections[rule.unit_kind]:
            facts = _facts(unit, known)
            if matches(rule.when, facts):
                findings.append(_finding(rule, unit, facts, policy))
    return tuple(findings)
