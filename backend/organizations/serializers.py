from catalog.models import Flag
from organizations.models import Organization, TenantFlagRelationship
from rest_framework import serializers


class TenantFlagRelationshipSerializer(serializers.ModelSerializer):
    flag_name = serializers.CharField(source="flag.name", read_only=True)

    class Meta:
        model = TenantFlagRelationship
        fields = [
            "id", "flag", "flag_name", "relationship_type",
            "registry_organization", "partner_organization", "status",
            "valid_from", "valid_until", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "flag_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "tenant_id", None):
            tenant_id = request.user.tenant_id
            self.fields["registry_organization"].queryset = Organization.objects.filter(tenant_id=tenant_id)
            self.fields["partner_organization"].queryset = Organization.objects.filter(tenant_id=tenant_id)
        self.fields["flag"].queryset = Flag.objects.filter(is_active=True)
