"""Pure orchestration across public domain APIs."""
from collections import Counter
from hashlib import sha256
from evidence_check.contracts.models import AuditReport, DocumentInput, Summary
from evidence_check.contracts.policy import Policy
from evidence_check.domains.document.api import parse_document
from evidence_check.domains.claim.api import normalize_claims
from evidence_check.domains.audit.api import evaluate_audit


def audit_document(document: DocumentInput, policy: Policy) -> AuditReport:
    bundle = parse_document(document, policy)
    claims = normalize_claims(bundle, document.claims, policy)
    findings = evaluate_audit(bundle, claims, policy)
    counts = Counter(finding.rule_id for finding in findings)
    return AuditReport(document_id=document.document_id, normalized_text=bundle.text,
        input_sha256=sha256(document.model_dump_json().encode()).hexdigest(),
        policy_version=policy.audit.version, audit_scope=policy.audit.audit_scope,
        policy_sha256=sha256(policy.model_dump_json().encode()).hexdigest(),
        disclaimer=policy.audit.disclaimer, findings=findings,
        summary=Summary(manual_claim_count=len(claims), sentence_count=len(bundle.sentences),
            citation_anchor_count=sum(len(sentence.citations) for sentence in bundle.sentences),
            finding_count=len(findings), by_rule=tuple(sorted(counts.items())),
            semantic_assessed_claim_count=0))
