"""
The Rule model — a persisted, data-only "WHEN / IF / THEN" definition.

WHY DATA, NOT CODE (the constraint that shapes everything else in this
app): a Rule is a row a future admin UI writes via a form, not a script
anyone writes. That's enforced structurally, not just by convention —
`conditions` is a JSON list of `{field, operator, value}` triples (never
an expression string to `eval()`), and `action_type` is a CharField
`choices=` restricted to a fixed, code-reviewed set of action
implementations (see `rules/actions.py`). There is no code path from
"data in this model" to "arbitrary code execution" anywhere in this app
— that's the entire point of it not being a scripting engine.
"""
from config.base_models import TenantScopedModel
from django.conf import settings
from django.db import models
from events.types import RULE_TRIGGERABLE_EVENT_TYPES


class Rule(TenantScopedModel):
    class ActionType(models.TextChoices):
        ACTIVATE_WORKFLOW_STEP = "activate_workflow_step", "Activate Workflow Step"
        CHANGE_SERVICE_REQUEST_STATE = "change_service_request_state", "Change ServiceRequest State"
        ASSIGN_ORGANIZATION = "assign_organization", "Assign Organization"
        CREATE_ACTIVITY_LOG_ENTRY = "create_activity_log_entry", "Create Activity Log Entry"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    event_type = models.CharField(
        max_length=100,
        choices=[(name, name) for name in RULE_TRIGGERABLE_EVENT_TYPES],
        help_text="WHEN: the domain event this rule listens for. Restricted to "
                   "events the rule engine is actually wired to (see "
                   "events.types.RULE_TRIGGERABLE_EVENT_TYPES) — a typo'd or "
                   "unsupported event name is rejected at save time, not "
                   "discovered later as a rule that silently never fires.",
    )

    conditions = models.JSONField(
        default=list, blank=True,
        help_text="IF: a list of {\"field\": ..., \"operator\": \"eq\"|\"neq\"|\"in\", "
                   "\"value\": ...} objects. ALL must match (implicit AND, no "
                   "OR/nesting — see rules/conditions.py for the exact contract "
                   "and the full list of supported `field` names per event_type). "
                   "An empty list means the rule fires on every occurrence of "
                   "event_type for this tenant.",
    )

    action_type = models.CharField(max_length=50, choices=ActionType.choices)
    action_config = models.JSONField(
        default=dict, blank=True,
        help_text="THEN: parameters for action_type — e.g. "
                   "{\"step_code\": \"bunker\"} for activate_workflow_step. "
                   "See rules/actions.py for the exact schema each action_type "
                   "expects.",
    )

    priority = models.IntegerField(
        default=0,
        help_text="Lower runs first when multiple rules match the same event. "
                   "Purely an ordering hint — rules should not depend on each "
                   "other's side effects within the same evaluation pass.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_rules",
    )

    class Meta:
        ordering = ["priority", "id"]
        indexes = [
            models.Index(fields=["tenant", "event_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.event_type} -> {self.action_type})"


class RuleExecutionLog(TenantScopedModel):
    """
    A record of one rule FIRING (conditions matched, action attempted).
    Separate from the general ActivityLog on purpose: this is rule-engine
    operational data (did the rule fire, did the action succeed) for
    debugging automations, not a business-fact audit trail — though a
    successful action's own domain-level consequence (e.g. a
    ServiceRequest status change) still gets its own ActivityLog entry
    via the normal event listeners, same as if a human had done it.
    """
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name="execution_logs")
    triggering_event_type = models.CharField(max_length=100)
    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE, related_name="rule_execution_logs",
    )
    succeeded = models.BooleanField()
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["service_request", "-created_at"])]

    def __str__(self):
        return f"{self.rule.name} on {self.service_request} ({'ok' if self.succeeded else 'failed'})"
