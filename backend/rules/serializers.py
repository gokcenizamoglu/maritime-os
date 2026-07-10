from rest_framework import serializers
from rules.actions import ACTION_REQUIRED_CONFIG_KEYS
from rules.conditions import OPERATORS
from rules.models import Rule


class RuleSerializer(serializers.ModelSerializer):
    """
    Validates `conditions` and `action_config` SHAPE at save time —
    not full semantic correctness (it can't know whether "bunker" is a
    real step_code for every ServiceType/Flag combination without
    running the rule), but catches the class of error that would
    otherwise only surface as a silent RuleExecutionLog failure much
    later: unknown operators, malformed condition dicts, missing
    required action_config keys.
    """
    class Meta:
        model = Rule
        fields = [
            "id", "name", "description", "event_type", "conditions",
            "action_type", "action_config", "priority", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_conditions(self, conditions):
        if not isinstance(conditions, list):
            raise serializers.ValidationError("conditions must be a list.")
        for condition in conditions:
            if not isinstance(condition, dict) or "field" not in condition or "value" not in condition:
                raise serializers.ValidationError(
                    'Each condition must be an object with at least "field" and "value" keys.'
                )
            operator = condition.get("operator", "eq")
            if operator not in OPERATORS:
                raise serializers.ValidationError(
                    f"Unknown operator '{operator}'. Supported: {sorted(OPERATORS)}."
                )
        return conditions

    def validate(self, attrs):
        action_type = attrs.get("action_type", getattr(self.instance, "action_type", None))
        action_config = attrs.get("action_config", getattr(self.instance, "action_config", {}) or {})
        required_keys = ACTION_REQUIRED_CONFIG_KEYS.get(action_type, set())
        missing = required_keys - set(action_config)
        if missing:
            raise serializers.ValidationError(
                {"action_config": f"Missing required key(s) for '{action_type}': {sorted(missing)}"}
            )
        return attrs
