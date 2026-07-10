"""
Condition evaluation: `Rule.conditions` (a list of {field, operator,
value} dicts) matched against the flat facts dict `rules.facts` builds
from an event. Implicit AND across the list — no OR, no nesting, no
negated groups. If that turns out to be too limiting later, the
extension point is adding a SECOND top-level key on the JSON (e.g.
`{"all": [...], "any": [...]}`) — a schema change, not a rewrite of
this evaluator, and explicitly deferred until there's a real rule that
needs it.

Only three operators, because the brief's own examples
(`service_type == "OwnerChange"`, `flag == "Panama"`) only need
equality/membership. Not building `>`, `<`, `contains`, regex, etc.
until a real rule needs them — every operator added is one more thing
that must be safe against every possible `field`/`value` type
combination.
"""
from typing import Any


def _op_eq(actual: Any, expected: Any) -> bool:
    return actual == expected


def _op_neq(actual: Any, expected: Any) -> bool:
    return actual != expected


def _op_in(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple, set)):
        raise ConditionConfigError(f"'in' operator requires a list value, got {type(expected).__name__}")
    return actual in expected


OPERATORS = {
    "eq": _op_eq,
    "neq": _op_neq,
    "in": _op_in,
}


class ConditionConfigError(Exception):
    """The condition itself is malformed (bad operator, bad value shape) —
    a Rule authoring/config problem, not a runtime data problem."""


class UnknownFactError(Exception):
    """The condition references a `field` this event type doesn't
    resolve any fact for — almost always a typo in the Rule's config."""


def evaluate_conditions(conditions: list[dict], facts: dict) -> bool:
    """
    Returns True only if EVERY condition matches. An empty `conditions`
    list matches unconditionally (a Rule with no IF clause always fires
    on its event, matching the brief's `IF` being effectively optional).
    """
    for condition in conditions:
        field = condition.get("field")
        operator = condition.get("operator", "eq")
        expected = condition.get("value")

        if field not in facts:
            raise UnknownFactError(
                f"Condition references unknown field '{field}'. "
                f"Available for this event: {sorted(facts)}"
            )
        op_fn = OPERATORS.get(operator)
        if op_fn is None:
            raise ConditionConfigError(
                f"Unknown operator '{operator}'. Available: {sorted(OPERATORS)}"
            )
        if not op_fn(facts[field], expected):
            return False
    return True
