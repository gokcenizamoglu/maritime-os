from rest_framework import serializers
from workflow.models import WorkflowStepInstance


class WorkflowStepInstanceSerializer(serializers.ModelSerializer):
    step_name = serializers.CharField(source="step_template.name", read_only=True)
    step_code = serializers.CharField(source="step_template.code", read_only=True)
    is_external = serializers.BooleanField(source="step_template.is_external", read_only=True)
    depends_on_codes = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowStepInstance
        fields = [
            "id", "step_code", "step_name", "status", "is_external",
            "assigned_organization", "started_at", "completed_at", "depends_on_codes",
        ]

    def get_depends_on_codes(self, obj):
        return list(obj.step_template.depends_on.values_list("code", flat=True))


class WorkflowStepTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WorkflowStepInstance.Status.choices)
