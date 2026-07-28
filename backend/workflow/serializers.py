from rest_framework import serializers
from catalog.models import TenantServiceOffering
from workflow.models import OperationTemplate, OperationTemplateVersion, WorkflowStepInstance, WorkflowStepTemplate


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


class OperationTemplateSerializer(serializers.ModelSerializer):
    service_offering_name = serializers.CharField(source="service_offering.display_name", read_only=True)

    class Meta:
        model = OperationTemplate
        fields = [
            "id", "service_offering", "service_offering_name", "name", "code",
            "description", "is_active", "is_default", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "service_offering_name", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if tenant_id:
            self.fields["service_offering"].queryset = TenantServiceOffering.objects.filter(
                tenant_id=tenant_id,
            )


class OperationTemplateVersionSerializer(serializers.ModelSerializer):
    template_code = serializers.CharField(source="operation_template.code", read_only=True)

    class Meta:
        model = OperationTemplateVersion
        fields = [
            "id", "operation_template", "template_code", "version_number", "status",
            "published_at", "created_by", "published_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "version_number", "status", "published_at", "created_by", "published_by",
            "created_at", "updated_at", "template_code",
        ]


class WorkflowStepTemplateDefinitionSerializer(serializers.ModelSerializer):
    depends_on_codes = serializers.ListField(
        child=serializers.SlugField(max_length=50), required=False, allow_empty=True,
    )

    class Meta:
        model = WorkflowStepTemplate
        fields = [
            "id", "operation_template_version", "code", "name", "is_external",
            "responsible_organization_type", "depends_on_codes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if tenant_id:
            self.fields["operation_template_version"].queryset = OperationTemplateVersion.objects.filter(
                operation_template__service_offering__tenant_id=tenant_id,
            )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["depends_on_codes"] = list(instance.depends_on.values_list("code", flat=True))
        return data
