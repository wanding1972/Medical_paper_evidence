"""Full pure workflow, external models injected through a stable port."""
from hashlib import sha256
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.product import ProductRequest, ProductReport, ModelPort, ModelAdmissionFacts
from evidence_check.contracts.predicates import enforce
from evidence_check.contracts.product_policy import ProductPolicy
from evidence_check.domains.document.api import parse_document
from evidence_check.domains.claim.api import normalize_claims, extract_candidates
from evidence_check.domains.evidence.api import retrieve, validate_sources
from evidence_check.domains.audit.api import assess


def run_audit(request: ProductRequest, legacy: Policy, policy: ProductPolicy, model: ModelPort | None = None) -> ProductReport:
    bundle=parse_document(request.document,legacy)
    validate_sources(request.sources)
    enforce(policy.model_gates,ModelAdmissionFacts(requested=model is not None,enabled=policy.model.enabled,consent=request.model_consent))
    candidates=request.document.claims
    if request.auto_candidates:
        candidates=model.extract(request.document).claims if model is not None else extract_candidates(bundle,policy)
    if len(candidates)>policy.limits.max_claims:raise InputError('too_many_claims','Candidate count exceeds configured limit.')
    for candidate in candidates:
        if candidate.claim_type is not None and candidate.claim_type not in policy.claim_types:
            raise InputError('invalid_claim_type','Candidate claim type is not configured.')
        if candidate.assertion_strength is not None and candidate.assertion_strength not in policy.assertion_strengths:
            raise InputError('invalid_assertion_strength','Candidate assertion strength is not configured.')
    if len(request.observations)>policy.limits.max_observations:raise InputError('too_many_observations','Too many comparisons.')
    claims=normalize_claims(bundle,candidates,legacy)
    starts={c.location.char_start for c in claims}
    if any(o.claim_start not in starts for o in request.observations):raise InputError('orphan_observation','Comparison does not belong to a selected claim.')
    assessments=[]
    for claim in claims:
        evidence=retrieve(claim,request.sources,policy)
        observations=tuple(o for o in request.observations if o.claim_start==claim.location.char_start)
        if model is not None and evidence and not observations:
            observations=model.compare(claim,evidence).observations
        assessments.append(assess(claim,tuple(r.reference_id for r in bundle.references),request.sources,
                                  evidence,observations,legacy,policy))
    return ProductReport(document_id=bundle.document_id,normalized_text=bundle.text,
        input_sha256=sha256(request.model_dump_json().encode()).hexdigest(),
        policy_sha256=sha256((legacy.model_dump_json()+policy.model_dump_json()).encode()).hexdigest(),
        policy_version=policy.version,audit_scope=policy.audit_scope,disclaimer=policy.disclaimer,
        candidate_notice=policy.candidate_notice,assessments=tuple(assessments),sources=request.sources,
        model_name=model.name if model is not None else None,prompt_version=policy.model.prompt_version)
