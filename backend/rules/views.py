from config.permissions import IsSameTenantObject, IsTenantMember
from events.types import RULE_TRIGGERABLE_EVENT_TYPES
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rules.actions import ACTION_REQUIRED_CONFIG_KEYS, ACTIONS
from rules.conditions import OPERATORS
from rules.facts import EVENT_FACT_FIELDS
from rules.models import Rule
from rules.serializers import RuleSerializer


class RuleViewSet(viewsets.ModelViewSet):
    """
    No drag-and-drop builder here — just a plain CRUD surface a future
    UI (or, today, a support engineer / seed script) uses to author
    rules. `perform_create` stamps `tenant`/`created_by` server-side so
    a rule can never be created for another tenant regardless of what
    the request body contains.
    """
    serializer_class = RuleSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject]

    def get_queryset(self):
        return Rule.objects.filter(tenant=self.request.user.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant, created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="metadata")
    def rule_metadata(self, request):
        """
        GET /api/rules/metadata/ — read-only vocabulary for a rule-builder
        UI: which events a Rule can trigger on, which facts each exposes
        for `conditions`, which actions exist and what `action_config`
        they require, and which condition operators are supported.

        Every value below is read FROM an existing engine constant
        (RULE_TRIGGERABLE_EVENT_TYPES, EVENT_FACT_FIELDS, ACTIONS,
        ACTION_REQUIRED_CONFIG_KEYS, OPERATORS, Rule.ActionType) — this
        endpoint formats them as JSON, it does not define or duplicate
        them. Adding a new event/action/operator to those existing
        registries makes it appear here automatically; nothing in this
        method needs to change.
        """
        action_labels = dict(Rule.ActionType.choices)
        return Response({
            "events": [
                {
                    "value": event_name,
                    "label": event_name.replace(".", " ").replace("_", " ").title(),
                    "available_facts": EVENT_FACT_FIELDS.get(event_name, []),
                }
                for event_name in RULE_TRIGGERABLE_EVENT_TYPES
            ],
            "actions": [
                {
                    "action_type": action_type,
                    "label": action_labels.get(action_type, action_type),
                    "required_config_fields": sorted(ACTION_REQUIRED_CONFIG_KEYS.get(action_type, set())),
                }
                for action_type in ACTIONS
            ],
            "operators": sorted(OPERATORS),
        })
