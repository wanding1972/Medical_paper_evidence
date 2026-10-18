"""Typed, immutable policy. Operators are finite and never execute expressions."""
import re
from typing import Literal, Self, get_args
from pydantic import field_validator, model_validator
from evidence_check.contracts.models import (
    DTO, DocumentFacts, CitationFacts, ClaimFacts, FileFacts, AuditFacts, ParserFacts,
)


class Condition(DTO):
    field: str
    op: Literal["eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "truthy", "falsy"]
    value: str | int | bool | tuple[str, ...] | None

    @model_validator(mode="after")
    def check_operand(self) -> Self:
        if self.op in ("gt", "ge", "lt", "le") and type(self.value) is not int:
            raise ValueError("Ordered conditions require an integer")
        if self.op in ("in", "not_in") and not isinstance(self.value, tuple):
            raise ValueError("Membership conditions require a tuple")
        if self.op in ("eq", "ne") and isinstance(self.value, tuple):
            raise ValueError("Equality conditions require a scalar")
        return self


class Gate(DTO):
    when: tuple[Condition, ...]
    code: str
    message: str

    @field_validator("when")
    @classmethod
    def nonempty(cls, value: tuple[Condition, ...]) -> tuple[Condition, ...]:
        if not value:
            raise ValueError("Gate conditions must be explicit")
        return value


class Rule(DTO):
    id: str
    enabled: bool
    unit_kind: Literal["sentence", "claim"]
    when: tuple[Condition, ...]
    label: str
    severity: str
    message: str
    guidance: str
    reference_field: Literal["citation_ids", "unresolved_ids", "resolved_ids"]

    @model_validator(mode="after")
    def check_enabled(self) -> Self:
        if self.enabled and not self.when:
            raise ValueError("Cannot enable unimplemented rules without fact conditions")
        return self


class RulesPolicy(DTO):
    version: str
    labels: tuple[str, ...]
    severities: tuple[str, ...]
    review_status: str
    audit_scope: str
    disclaimer: str
    rules: tuple[Rule, ...]

    @model_validator(mode="after")
    def check_rules(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate rule IDs")
        for rule in self.rules:
            if rule.label not in self.labels or rule.severity not in self.severities:
                raise ValueError("Rule label/severity outside configured vocabulary")
            validate_conditions(rule.when, AuditFacts)
        return self


class SecurityPolicy(DTO):
    external_llm_enabled: Literal[False]
    patient_data_allowed: Literal[False]
    pii_detection_status: str
    persist_uploads: Literal[False]
    original_file_retention_hours: int
    parsed_text_retention_hours: int
    external_llm_requires_consent: bool

class Formats(DTO):
    markdown: tuple[str, ...]
    docx: tuple[str, ...]


class LimitsPolicy(DTO):
    version: str
    document_gates: tuple[Gate, ...]
    claim_gates: tuple[Gate, ...]
    citation_gates: tuple[Gate, ...]
    file_gates: tuple[Gate, ...]
    parser_gates: tuple[Gate, ...]
    security: SecurityPolicy
    formats: Formats
    single_section_declaration_required: bool

    @model_validator(mode="after")
    def check_gates(self) -> Self:
        for gates, facts in (
            (self.document_gates, DocumentFacts), (self.claim_gates, ClaimFacts),
            (self.citation_gates, CitationFacts), (self.file_gates, FileFacts),
            (self.parser_gates, ParserFacts),
        ):
            fields = {condition.field for gate in gates for condition in gate.when}
            if fields != set(facts.model_fields):
                raise ValueError("Admission configuration must cover the complete fact contract")
            for gate in gates:
                validate_conditions(gate.when, facts)
        suffixes = self.formats.markdown + self.formats.docx
        if len(suffixes) != len(set(suffixes)):
            raise ValueError("Ambiguous format mapping")
        return self


class ParsingPolicy(DTO):
    version: str
    citation_pattern: str
    bracket_pattern: str
    numeric_bracket_pattern: str
    citation_separator_pattern: str
    range_separator: str
    sentence_pattern: str
    chinese_pattern: str
    english_word_pattern: str
    heading_pattern: str
    pii_patterns: tuple[str, ...]
    paragraph_separator: str
    strip_bom: bool
    docx_unsupported_xpath: str

    @model_validator(mode="after")
    def compile_patterns(self) -> Self:
        for name in type(self).model_fields:
            if name.endswith("_pattern"):
                re.compile(getattr(self, name))
        for pattern in self.pii_patterns:
            re.compile(pattern)
        if re.compile(self.citation_pattern).groups != 1:
            raise ValueError("Citation grammar must have one content group")
        if not self.range_separator or not self.paragraph_separator:
            raise ValueError("Separators cannot be empty")
        return self


class RetrievalScope(DTO):
    cited_references_only: bool
    require_resolved_reference: bool
    require_readable_fulltext: bool
    allow_external_search: bool
    allow_abstract_as_evidence: bool
    allow_metadata_as_evidence: bool
    require_source_location: bool


class RetrievalTuning(DTO):
    method: str
    top_k: int
    validated: bool


class Reranking(DTO):
    enabled: Literal[False]


class EvidencePolicy(DTO):
    preserve_original_text: bool
    require_page: bool
    require_source_file_id: bool
    validate_against_original: bool


class RetrievalPolicy(DTO):
    version: str
    implemented: Literal[False]
    scope: RetrievalScope
    retrieval: RetrievalTuning
    reranking: Reranking
    evidence: EvidencePolicy

class AcceptancePolicy(DTO):
    version: str
    gold_data_available: bool
    minimum_development_claims: int
    independent_claims_per_language: int
    language_modes: tuple[str, ...]
    citation_accuracy_min: float
    integrity_precision_min: float
    semantic_warning_precision_min: float
    task_seconds_max: int
    blind_split_required: bool
    template_is_acceptance_data: bool
    metrics: tuple[str, ...]
    runtime_fixture_checks_are_not_accuracy_claims: bool


class Policy(DTO):
    audit: RulesPolicy
    limits: LimitsPolicy
    parsing: ParsingPolicy
    retrieval: RetrievalPolicy
    acceptance: AcceptancePolicy

    @model_validator(mode="after")
    def consistent_versions(self) -> Self:
        versions = {getattr(self, name).version for name in type(self).model_fields}
        if len(versions) != 1:
            raise ValueError("Policy versions differ")
        return self


def validate_conditions(conditions: tuple[Condition, ...], facts_type: type[DTO]) -> None:
    for condition in conditions:
        field = facts_type.model_fields.get(condition.field)
        if field is None:
            raise ValueError("Unknown fact field")
        if condition.op in ("gt", "ge", "lt", "le"):
            if field.annotation not in (int, int | None):
                raise ValueError("Ordered condition requires numeric facts")
        if condition.op in ("in", "not_in") and field.annotation is not str:
            raise ValueError("Membership condition requires string facts")
        if condition.op in ("eq", "ne"):
            types = get_args(field.annotation) or (field.annotation,)
            if type(condition.value) not in types:
                raise ValueError("Equality operand must match the fact's exact type")
