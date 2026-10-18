"""Product strategy schema: values supplied exclusively by product.json."""
import re
from typing import Self, Literal
from pydantic import model_validator
from evidence_check.contracts.models import DTO
from evidence_check.contracts.policy import Condition, Gate, AcceptancePolicy, validate_conditions
from evidence_check.contracts.product import DecisionFacts, ObservationCounts, Observation, ParagraphFacts, ModelAdmissionFacts


class CandidatePattern(DTO):
    pattern: str
    claim_type: str
    assertion_strength: str


class RelationVocabulary(DTO):
    support_relation: tuple[str, ...]
    scope_relation: tuple[str, ...]
    causal_relation: tuple[str, ...]
    direction_relation: tuple[str, ...]
    numeric_relation: tuple[str, ...]


class Origins(DTO):
    local: str
    human: str
    model: str


class UploadLimits(DTO):
    total_upload_bytes: int
    file_bytes: int
    file_count: int
    pdf_pages: int
    pdf_text_chars: int
    max_claims: int
    max_tasks: int
    request_bytes: int
    max_context_chars: int
    max_observations: int


class Synonym(DTO):
    term: str
    alternatives: tuple[str, ...]


class SearchPolicy(DTO):
    token_pattern: str
    k1: float
    b: float
    top_k: int
    minimum_score: float
    min_paragraph_chars: int
    excluded_section_pattern: str
    synonyms: tuple[Synonym, ...]
    paragraph_gates: tuple[Gate, ...]
    body_section_pattern: str


class CounterDefinition(DTO):
    fact: str
    field: str
    value: str


class Trigger(DTO):
    rule_id: str
    when: tuple[Condition, ...]
    reference_field: Literal['citation_ids','resolved_ids','unresolved_ids','available_ids','unavailable_ids']


class Decision(DTO):
    when: tuple[Condition, ...]
    label: str


class Lifecycle(DTO):
    queued: str
    running: str
    done: str
    failed: str
    retention_hours: int
    poll_seconds: float
    cleanup_seconds: int
    retry_limit: int
    ui_poll_seconds: float


class ModelPolicy(DTO):
    enabled: bool
    endpoint_env: str
    key_env: str
    name_env: str
    prompt_version: str
    timeout_seconds: int
    temperature: float
    max_response_tokens: int
    extract_system: str
    compare_system: str


class AuthPolicy(DTO):
    cookie_name: str
    session_hours: int
    failed_login_delay_seconds: float


class UIOption(DTO):
    value: str
    label: str


class UIField(DTO):
    key: str
    label: str
    options: tuple[UIOption, ...]


class UIPolicy(DTO):
    timezone: str
    fields: tuple[UIField, ...]
    labels: tuple[UIOption, ...]
    states: tuple[UIOption, ...]
    source_errors: tuple[UIOption, ...]
    origins: tuple[UIOption, ...]


class PrecisionRequirement(DTO):
    rule_id: str
    minimum_field: str


class EvaluationPolicy(DTO):
    accepted_statuses: tuple[str, ...]
    precision_requirements: tuple[PrecisionRequirement, ...]
    placeholder_pattern: str


class ProductPolicy(DTO):
    version: str
    title: str
    subtitle: str
    disclaimer: str
    audit_scope: str
    candidate_patterns: tuple[CandidatePattern, ...]
    claim_types: tuple[str, ...]
    assertion_strengths: tuple[str, ...]
    qualifier_keys: tuple[str, ...]
    relations: RelationVocabulary
    unknown_relation: str
    origins: Origins
    limits: UploadLimits
    retrieval: SearchPolicy
    counters: tuple[CounterDefinition, ...]
    rule_triggers: tuple[Trigger, ...]
    decisions: tuple[Decision, ...]
    default_label: str
    lifecycle: Lifecycle
    model: ModelPolicy
    feedback_states: tuple[str, ...]
    auth: AuthPolicy
    format_options: tuple[str, ...]
    source_error_label: str
    candidate_notice: str
    ui: UIPolicy
    evaluation: EvaluationPolicy
    model_gates: tuple[Gate, ...]

    @model_validator(mode='after')
    def valid(self) -> Self:
        for item in self.candidate_patterns:
            re.compile(item.pattern)
            if item.claim_type not in self.claim_types or item.assertion_strength not in self.assertion_strengths:
                raise ValueError('Candidate vocabulary mismatch')
        re.compile(self.retrieval.token_pattern)
        re.compile(self.retrieval.excluded_section_pattern)
        re.compile(self.retrieval.body_section_pattern)
        re.compile(self.evaluation.placeholder_pattern)
        for requirement in self.evaluation.precision_requirements:
            field=AcceptancePolicy.model_fields.get(requirement.minimum_field)
            if field is None or field.annotation is not float:raise ValueError('Invalid acceptance threshold reference')
        for row in (*self.decisions, *self.rule_triggers):
            if not row.when: raise ValueError('Empty decision conditions')
            validate_conditions(row.when, DecisionFacts)
        for gate in self.retrieval.paragraph_gates: validate_conditions(gate.when, ParagraphFacts)
        for gate in self.model_gates:validate_conditions(gate.when,ModelAdmissionFacts)
        if {c.field for g in self.model_gates for c in g.when} != set(ModelAdmissionFacts.model_fields):
            raise ValueError('Incomplete model admission policy')
        for counter in self.counters:
            if counter.fact not in DecisionFacts.model_fields or counter.field not in type(self.relations).model_fields:
                raise ValueError('Unknown counter field')
            if counter.value not in getattr(self.relations,counter.field): raise ValueError('Counter vocabulary mismatch')
        if len({c.fact for c in self.counters}) != len(self.counters):raise ValueError('Duplicate counters')
        if len({t.rule_id for t in self.rule_triggers}) != len(self.rule_triggers):raise ValueError('Duplicate rule triggers')
        if {c.fact for c in self.counters} != set(ObservationCounts.model_fields):raise ValueError('Incomplete observation counters')
        if any(value <= 0 for value in self.limits.model_dump().values()):raise ValueError('Limits must be positive')
        if self.retrieval.k1 <= 0 or not 0 <= self.retrieval.b <= 1 or self.retrieval.top_k <= 0:
            raise ValueError('Invalid BM25 parameters')
        states=(self.lifecycle.queued,self.lifecycle.running,self.lifecycle.done,self.lifecycle.failed)
        if len(set(states)) != len(states):raise ValueError('Duplicate lifecycle states')
        if self.lifecycle.retention_hours <= 0 or self.lifecycle.poll_seconds <= 0 or self.lifecycle.cleanup_seconds <= 0:
            raise ValueError('Invalid lifecycle intervals')
        return self
