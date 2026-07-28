from organizations.models import TenantFlagRelationship
from rest_framework import serializers

from catalog.models import Flag, ServiceType, TenantServiceOffering
from workflow.models import OperationTemplate


class TenantServiceOfferingSerializer(serializers.ModelSerializer):
    service_type_name = serializers.CharField(source="service_type.name", read_only=True)
    flag_name = serializers.CharField(source="flag.name", read_only=True, allow_null=True)
    class Meta:
        model = TenantServiceOffering
        fields = [
            "id", "service_type", "service_type_name", "flag", "flag_name",
            "flag_relationship", "display_name", "description", "status",
            "accepts_new_requests", "valid_from", "valid_until",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "service_type_name", "flag_name", "created_at", "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if tenant_id:
            self.fields["flag_relationship"].queryset = TenantFlagRelationship.objects.filter(
                tenant_id=tenant_id,
            )
        self.fields["service_type"].queryset = ServiceType.objects.filter(is_active=True)
        self.fields["flag"].queryset = Flag.objects.filter(is_active=True)

class OperationTemplateSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationTemplate
        fields = ["id", "name", "code", "description", "is_active", "is_default"]
