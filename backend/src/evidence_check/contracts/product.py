"""Stable product DTO and external effect protocols."""
from typing import Protocol
from evidence_check.contracts.models import DTO, ClaimCandidate, ClaimRecord, DocumentInput, Finding, Location


class SourceParagraph(DTO):
    paragraph: int
    start: int
    end: int
    excluded: bool


class SourcePage(DTO):
    page: int
    text: str
    paragraphs: tuple[SourceParagraph, ...]


class SourceDocument(DTO):
    reference_id: int
    source_file_id: str
    sha256: str
    pages: tuple[SourcePage, ...]
    error_code: str | None = None


class EvidenceSpan(DTO):
    span_id: str
    reference_id: int
    source_file_id: str
    page: int
    paragraph: int
    start: int
    end: int
    text: str
    score: float


class Observation(DTO):
    claim_start: int
    evidence_ids: tuple[str, ...]
    support_relation: str
    scope_relation: str
    causal_relation: str
    direction_relation: str
    numeric_relation: str
    rationale: str
    origin: str


class ObservationCounts(DTO):
    support_count: int
    partial_count: int
    opposition_count: int
    unknown_count: int
    scope_count: int
    causality_count: int
    direction_count: int
    numeric_count: int
    scope_unknown_count: int
    causal_unknown_count: int
    direction_unknown_count: int
    numeric_unknown_count: int


class DecisionFacts(ObservationCounts):
    citation_count: int
    unresolved_count: int
    available_count: int
    unavailable_count: int
    evidence_count: int
    comparison_count: int
    unreviewed_source_count: int


class ParagraphFacts(DTO):
    table_overlap_count: int
    abstract: bool


class SubmissionHeader(DTO):
    authorized: bool
    single_section: bool


class ModelAdmissionFacts(DTO):
    requested: bool
    enabled: bool
    consent: bool


class ClaimAssessment(DTO):
    claim: ClaimRecord
    evidence: tuple[EvidenceSpan, ...]
    observations: tuple[Observation, ...]
    findings: tuple[Finding, ...]
    predicted_label: str
    review_status: str
    facts: DecisionFacts


class ProductRequest(DTO):
    document: DocumentInput
    sources: tuple[SourceDocument, ...] = ()
    observations: tuple[Observation, ...] = ()
    auto_candidates: bool = True
    model_consent: bool = False


class ProductReport(DTO):
    document_id: str
    normalized_text: str
    input_sha256: str
    policy_sha256: str
    policy_version: str
    audit_scope: str
    disclaimer: str
    candidate_notice: str
    assessments: tuple[ClaimAssessment, ...]
    sources: tuple[SourceDocument, ...]
    model_name: str | None
    prompt_version: str


class CandidateBatch(DTO):
    claims: tuple[ClaimCandidate, ...]


class ObservationBatch(DTO):
    observations: tuple[Observation, ...]


class ModelPort(Protocol):
    name: str

    def extract(self, document: DocumentInput) -> CandidateBatch: ...
    def compare(self, claim: ClaimRecord, evidence: tuple[EvidenceSpan, ...]) -> ObservationBatch: ...
