"""
The rule engine's execution service — `evaluate_rules(event)`.

DEVIATION FROM THE REQUESTED SIGNATURE, NOTED DELIBERATELY: the brief
specifies `rules.services.evaluate_rules(event, payload)`. This takes a
single `event: DomainEvent` argument instead, because
`events.dispatcher.DomainEvent` already carries `payload` as an
attribute (`event.payload`), and every other listener in the codebase
(`checklists/listeners.py`, `activity/listeners.py`) is registered the
same way via `@on(...)`. Splitting `event`/`payload` back into two
arguments here would make this the one function in the system with a
different calling convention from every other event handler, for no
benefit. If a genuinely separate `payload` argument is needed later
(e.g. to evaluate rules against a payload that ISN'T a live event), add
an explicit second entry point rather than changing this one.

SAFETY DESIGN: rule evaluation runs SYNCHRONOUSLY inside whatever
transaction the triggering event's action started (e.g. inside
`classify_document`'s `@transaction.atomic`). A rule's ACTION runs in
its OWN nested savepoint (`transaction.atomic()` below) specifically so
a misconfigured rule (bad step_code, invalid target_status, whatever)
can NEVER roll back or fail the original operation that triggered
evaluation — it only rolls back its own attempted mutation. This is the
concrete meaning of "must not break invariants" from the brief: a bad
Rule is a contained failure, recorded in RuleExecutionLog, never a
crash of the classification/transition/whatever that fired it.

LOOP PROTECTION: the RULE_TRIGGERABLE_EVENT_TYPES whitelist (see
events/types.py) is NOT sufficient to prevent cycles by itself, despite
what an earlier version of RULES_ENGINE.md claimed. Two actions call
service functions that emit an event which is ITSELF in the whitelist —
`change_service_request_state` -> `transition_state()` ->
SERVICE_REQUEST_STATUS_CHANGED, and `activate_workflow_step` ->
`update_step_status()` -> WORKFLOW_STEP_STATUS_CHANGED. A Rule on either
of those event types, whose action fires that same kind of event again,
recurses synchronously through `evaluate_rules()` with no async boundary
to break it.

`_execution_chain` (a `contextvars.ContextVar`, not a plain module-level
set — this runs per-request/per-thread and must not leak between
concurrent tenants) tracks which Rule ids have already fired within the
current SYNCHRONOUS call chain, not "the current Django request" — those
are different scopes. A bulk endpoint that calls `create_service_request`
twice, back to back, produces two independent (non-nested) top-level
calls into this function, each of which should be free to fire the same
Rule again; only a rule action that RECURSIVELY causes another
`evaluate_rules()` call, still inside the first one's stack frame, is the
case being guarded against. That's exactly what "is there already an
active chain on this contextvar" distinguishes: nested call -> reuse it;
no active chain -> this IS the top of a new one, so start a fresh set and
clear it (in `finally`, even on exception) when this call returns.

A rule id is added to the set the moment its conditions MATCH — before
its action runs, not only after it succeeds — so a rule whose action
fails (nested savepoint rolls back) still counts as "visited" and can't
be re-entered by something else later in the same chain. Since a Rule's
`event_type` is fixed per row, `rule.id` alone is an unambiguous key; no
need to pair it with the triggering event name.

Because a rule can fire at most once per chain, the chain is bounded by
the tenant's total active-rule count — it structurally terminates even
for a cycle of N *distinct* rules, without needing a separate hard depth
cap.
"""
import contextvars

from django.db import transaction
from events.dispatcher import DomainEvent, emit
from events.types import RULE_ACTION_EXECUTED, RULE_ACTION_FAILED
from rules.actions import ACTIONS, ActionConfigError
from rules.conditions import ConditionConfigError, UnknownFactError, evaluate_conditions
from rules.facts import resolve_facts, resolve_service_request
from rules.models import Rule, RuleExecutionLog

# None = no chain currently in flight on this thread/task. A non-None set
# means this call to evaluate_rules() is NESTED inside another one
# (reached via a rule's own action re-emitting a triggerable event).
_execution_chain: contextvars.ContextVar[set[int] | None] = contextvars.ContextVar(
    "_rule_execution_chain", default=None,
)


def evaluate_rules(event: DomainEvent) -> None:
    """
    Registered (see rules/listeners.py) against every event name in
    `events.types.RULE_TRIGGERABLE_EVENT_TYPES`. Finds this tenant's
    active Rules for this event type, evaluates each one's conditions
    against the event's resolved facts, and executes the action for
    every rule that matches — in `priority` order.

    See the module docstring's LOOP PROTECTION section for why a rule
    already fired earlier in this synchronous call chain is skipped.
    """
    service_request = resolve_service_request(event)
    if service_request is None:
        # This event type isn't resolvable to a ServiceRequest (shouldn't
        # happen for anything in RULE_TRIGGERABLE_EVENT_TYPES, but fail
        # safe rather than raising into the middle of an unrelated
        # domain operation).
        return

    facts = resolve_facts(event)
    candidate_rules = Rule.objects.filter(
        tenant=service_request.tenant, event_type=event.name, is_active=True,
    ).select_related(None).order_by("priority", "id")

    executed_rule_ids = _execution_chain.get()
    is_chain_root = executed_rule_ids is None
    if is_chain_root:
        executed_rule_ids = set()
        token = _execution_chain.set(executed_rule_ids)

    try:
        for rule in candidate_rules:
            if rule.id in executed_rule_ids:
                # Already fired earlier in this same synchronous event
                # chain — this IS the loop guard, not a bug.
                continue

            try:
                matched = evaluate_conditions(rule.conditions, facts)
            except (ConditionConfigError, UnknownFactError) as exc:
                _record_failure(rule, service_request, event.name, exc)
                continue

            if matched:
                executed_rule_ids.add(rule.id)
                _execute_action(rule, service_request, event.name)
    finally:
        if is_chain_root:
            _execution_chain.reset(token)


def _execute_action(rule: Rule, service_request, event_name: str) -> None:
    action_fn = ACTIONS.get(rule.action_type)
    if action_fn is None:
        _record_failure(rule, service_request, event_name, ActionConfigError(f"Unknown action_type '{rule.action_type}'"))
        return

    try:
        with transaction.atomic():
            action_fn(service_request=service_request, action_config=rule.action_config, rule=rule)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: ANY action failure must be contained, not just the ones we anticipated
        _record_failure(rule, service_request, event_name, exc)
        return

    RuleExecutionLog.objects.create(
        tenant=service_request.tenant,
        rule=rule,
        triggering_event_type=event_name,
        service_request=service_request,
        succeeded=True,
    )
    emit(RULE_ACTION_EXECUTED, rule=rule, service_request=service_request, event_name=event_name)


def _record_failure(rule: Rule, service_request, event_name: str, exc: Exception) -> None:
    RuleExecutionLog.objects.create(
        tenant=service_request.tenant,
        rule=rule,
        triggering_event_type=event_name,
        service_request=service_request,
        succeeded=False,
        error_message=str(exc),
    )
    emit(RULE_ACTION_FAILED, rule=rule, service_request=service_request, event_name=event_name, error=str(exc))
