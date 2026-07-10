# MaritimeOS — Rule Engine (Phase 1.3)

The "first 10% of Salesforce automation": event-driven, condition-based,
action-based. No scripting, no DSL, no async infra. New app: `rules`.

## What was added

| File | Role |
|---|---|
| `rules/models.py` | `Rule` (the WHEN/IF/THEN config) + `RuleExecutionLog` (operational audit — did it fire, did it succeed) |
| `rules/facts.py` | Turns a raw event's payload into a flat `{field: value}` dict, per event type |
| `rules/conditions.py` | Evaluates `Rule.conditions` (list of `{field, operator, value}`) against facts. Operators: `eq`, `neq`, `in`. AND-only. |
| `rules/actions.py` | THEN implementations — every one calls an EXISTING service function, never a raw model mutation |
| `rules/services.py` | `evaluate_rules(event)` — the execution engine |
| `rules/listeners.py` | Subscribes `evaluate_rules` to every event in `events.types.RULE_TRIGGERABLE_EVENT_TYPES` |
| `rules/serializers.py`, `views.py` | Plain tenant-scoped CRUD API (no builder UI) |
| `events/types.py` | Added `RULE_TRIGGERABLE_EVENT_TYPES` (whitelist), `RULE_ACTION_EXECUTED`, `RULE_ACTION_FAILED` |
| `activity/listeners.py` | One new handler: logs `RULE_ACTION_FAILED` to the case timeline |

## Design explanation

**Why a whitelist of triggerable events (`RULE_TRIGGERABLE_EVENT_TYPES`),
not "any event in the system"?** Two of the system's own events
(`service_request.status_changed`, `workflow_step.status_changed`) can
themselves be CAUSED by a rule's action — `change_service_request_state`
calls `transition_state()`, `activate_workflow_step` calls
`update_step_status()`, and both of those service functions emit an
event that IS in the whitelist. So the whitelist alone bounds WHICH
events are rule-triggerable; it does not by itself prevent a rule's
action from re-entering `evaluate_rules()` — a rule that changes a
ServiceRequest's status can trigger a second rule that changes it again,
recursing synchronously with no async boundary to break it. That
residual gap is closed separately, in `rules/services.py`: a
`contextvars`-scoped set of Rule ids already fired in the current
synchronous call chain, checked before each candidate rule executes (see
that module's LOOP PROTECTION docstring for the full design). The
whitelist and the chain-tracking set are two independent layers — the
whitelist means a future engineer has to deliberately opt a new event
in, not discover it's triggerable by accident; the chain-tracking set
means that even among already-whitelisted events, no rule can re-fire
within one synchronous chain.

**Why is "every action calls an existing service function" load-bearing,
not just tidy?** It's the entire safety argument. `activate_workflow_step`
doesn't set `step_instance.status = "active"; step_instance.save()` —
it calls `workflow.services.update_step_status()`, which runs
`workflow.state_machine.assert_step_transition_allowed()` first. A rule
therefore CANNOT force an illegal transition; it can only ask for the
same transition a human clicking a button could ask for, and gets the
same rejection if it's invalid. The same is true for
`change_service_request_state` (full guard registry — checklist/workflow
completeness) and `assign_organization` (role/organization_type
consistency). The rule engine adds a new caller of the service layer,
never a new way to bypass it.

**Why does a failing rule action run inside its own
`transaction.atomic()` savepoint?** Rule evaluation happens
SYNCHRONOUSLY inside the transaction of whatever triggered it (e.g.
`classify_document`'s). Without an isolated savepoint, a misconfigured
rule (a typo'd `step_code`, a `target_status` that isn't a legal
transition) would raise an exception that propagates all the way up and
rolls back the classification that triggered it — meaning a broken
automation rule could make a completely valid, human-initiated action
fail. The nested `atomic()` block means the failure is contained: only
the rule's own attempted mutation rolls back; the triggering operation
completes normally, and the failure is recorded in `RuleExecutionLog`
plus surfaced via `RULE_ACTION_FAILED` on the case timeline.

**Why AND-only conditions with just three operators?** Every example in
the brief (`service_type == "OwnerChange"`, `flag == "Panama"`,
`document_type == "BlueCard"`) is a flat equality check. Building OR/NOT
groups or a comparison operator set nobody's asked for yet is exactly
the "generic scripting engine" the brief explicitly rules out. The
extension point is documented in `rules/conditions.py`: if OR logic is
genuinely needed later, it's a new top-level JSON key
(`{"any": [...]}`), not a rewrite of the evaluator.

**Why `RuleExecutionLog` as a separate model instead of reusing
`ActivityLog`?** `ActivityLog` is a business-fact audit trail —
"what happened to this case." `RuleExecutionLog` is rule-ENGINE
operational data — "did this specific automation fire, and did it
work" — useful for debugging a misbehaving rule, not for a customer- or
ops-facing case history. A successful rule action still produces a
normal `ActivityLog` entry, because the underlying service function
(`update_step_status`, `transition_state`, ...) emits its own event
exactly as it would for a human-initiated action — see
`activity/listeners.py`'s comment on why `RULE_ACTION_EXECUTED` is
deliberately NOT separately logged to the timeline (it would duplicate
the entry the real action's own event already creates). A FAILED rule,
by contrast, produces no other event — so `RULE_ACTION_FAILED` is the
only path to timeline visibility for that case.

## How this extends without changing core structure

- **More conditions**: add an operator function + register it in
  `rules/conditions.OPERATORS`. `rules/serializers.py`'s validation
  picks it up automatically (it iterates the same dict).
- **More actions**: add a function + register it in
  `rules/actions.ACTIONS` (and `ACTION_REQUIRED_CONFIG_KEYS` for
  save-time validation). Must call an existing service-layer function —
  that's a code-review convention this file's docstring states
  explicitly, not something enforced by the type system, so it's worth
  keeping as an explicit review checklist item.
- **More triggerable events**: add the event name to
  `events.types.RULE_TRIGGERABLE_EVENT_TYPES` and a resolver function in
  `rules/facts.py`. `rules/listeners.py` picks it up automatically
  (it loops over the list).
- **A UI builder later**: it's a form over `RuleSerializer`'s fields —
  `event_type` (select from `RULE_TRIGGERABLE_EVENT_TYPES`),
  `conditions` (repeatable field/operator/value rows), `action_type`
  (select from `Rule.ActionType`), `action_config` (a small form per
  action type, informed by `ACTION_REQUIRED_CONFIG_KEYS`). None of this
  requires touching the engine itself.
