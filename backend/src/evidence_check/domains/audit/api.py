"""Audit public API."""
from evidence_check.contracts.models import ClaimRecord, DocumentBundle, Finding
from evidence_check.contracts.policy import Policy
from evidence_check.domains.audit.engine import evaluate


def evaluate_audit(bundle: DocumentBundle, claims: tuple[ClaimRecord, ...], policy: Policy) -> tuple[Finding, ...]:
    return evaluate(bundle, claims, policy)


from evidence_check.domains.audit.product import assess
