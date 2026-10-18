"""Finite, domain-independent predicate interpreter (not an expression language)."""
import operator
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import DTO
from evidence_check.contracts.policy import Condition, Gate

_COMPARATORS = {
    "eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
    "ge": operator.ge, "lt": operator.lt, "le": operator.le,
    "in": lambda left, right: left in right,
    "not_in": lambda left, right: left not in right,
    "truthy": lambda left, right: bool(left),
    "falsy": lambda left, right: not left,
}


def matches(conditions: tuple[Condition, ...], facts: DTO) -> bool:
    def compare(condition: Condition) -> bool:
        value = getattr(facts, condition.field)
        if value is None:
            return False
        return _COMPARATORS[condition.op](value, condition.value)
    return all(compare(condition) for condition in conditions)


def enforce(gates: tuple[Gate, ...], facts: DTO) -> None:
    for gate in gates:
        if matches(gate.when, facts):
            raise InputError(gate.code, gate.message)
