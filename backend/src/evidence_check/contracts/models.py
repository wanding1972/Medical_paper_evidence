"""Immutable boundary DTOs; business admission is configuration-driven."""
from pydantic import BaseModel, ConfigDict


class DTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Reference(DTO):
    reference_id: int
    title: str


class Qualifiers(DTO):
    population: str | None = None
    disease: str | None = None
    intervention_or_exposure: str | None = None
    outcome: str | None = None
    time: str | None = None


class ClaimCandidate(DTO):
    start: int
    end: int
    text: str
    claim_type: str | None = None
    assertion_strength: str | None = None
    qualifiers: Qualifiers = Qualifiers()


class DocumentInput(DTO):
    document_id: str
    text: str
    references: tuple[Reference, ...] = ()
    claims: tuple[ClaimCandidate, ...] = ()
    language_mode: str
    authorized: bool
    single_section: bool


class Location(DTO):
    paragraph_index: int
    sentence_index: int
    char_start: int
    char_end: int


class Citation(DTO):
    reference_ids: tuple[int, ...]
    location: Location


class Sentence(DTO):
    text: str
    location: Location
    citations: tuple[Citation, ...]


class DocumentBundle(DTO):
    document_id: str
    text: str
    sentences: tuple[Sentence, ...]
    references: tuple[Reference, ...]


class ClaimRecord(DTO):
    text: str
    location: Location
    citation_ids: tuple[int, ...]
    claim_type: str | None = None
    assertion_strength: str | None = None
    qualifiers: Qualifiers = Qualifiers()


class Finding(DTO):
    rule_id: str
    severity: str
    label: str
    location: Location
    claim_text: str
    citation_ids: tuple[int, ...]
    message: str
    guidance: str
    review_status: str


class Summary(DTO):
    manual_claim_count: int
    sentence_count: int
    citation_anchor_count: int
    finding_count: int
    by_rule: tuple[tuple[str, int], ...]
    semantic_assessed_claim_count: int


class AuditReport(DTO):
    document_id: str
    normalized_text: str
    input_sha256: str
    policy_version: str
    policy_sha256: str
    audit_scope: str
    disclaimer: str
    findings: tuple[Finding, ...]
    summary: Summary


class DocumentFacts(DTO):
    authorized: bool
    single_section: bool
    language_mode: str
    text_length: int
    chinese_chars: int
    english_words: int
    reference_count: int
    duplicate_reference_count: int
    minimum_reference_id: int | None
    empty_title_count: int
    heading_count: int
    pii_match_count: int


class CitationFacts(DTO):
    minimum_id: int | None
    descending_count: int
    expanded_count: int
    malformed_count: int
    maximum_token_length: int


class ParserFacts(DTO):
    unparsed_chars: int


class ClaimFacts(DTO):
    start: int
    end_overflow: int
    span_length: int
    text_matches: bool
    containing_sentence_count: int
    omitted_citation_count: int
    overlap_count: int


class FileFacts(DTO):
    suffix: str
    size_bytes: int
    expanded_bytes: int
    unsupported_structure_count: int


class AuditFacts(DTO):
    citation_ids: tuple[int, ...]
    unresolved_ids: tuple[int, ...]
    resolved_ids: tuple[int, ...]
    citation_count: int
    unresolved_count: int
    resolved_count: int
