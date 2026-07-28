from organizations.models import TenantFlagRelationship
from rest_framework import serializers

from catalog.models import Flag, ServiceType, TenantServiceOffering
from workflow.models import OperationTemplate, OperationTemplateVersion


class TenantServiceOfferingSerializer(serializers.ModelSerializer):
    service_type_name = serializers.CharField(source="service_type.name", read_only=True)
    flag_name = serializers.CharField(source="flag.name", read_only=True, allow_null=True)
    flag_relationship_label = serializers.SerializerMethodField()
    template_variants = serializers.SerializerMethodField()

    class Meta:
        model = TenantServiceOffering
        fields = [
            "id", "service_type", "service_type_name", "flag", "flag_name",
            "flag_relationship", "flag_relationship_label", "display_name", "description", "status",
            "accepts_new_requests", "valid_from", "valid_until", "template_variants",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "service_type_name", "flag_name", "flag_relationship_label", "template_variants",
            "created_at", "updated_at",
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

    def get_template_variants(self, obj):
        variants = []
        for template in obj.operation_templates.all():
            published_versions = getattr(template, "published_versions", None)
            if published_versions is None:
                published_versions = list(
                    template.versions.filter(
                        status=OperationTemplateVersion.Status.PUBLISHED,
                    ).order_by("-version_number")[:1]
                )
            latest_published = published_versions[0] if published_versions else None
            if not template.is_active or latest_published is None:
                continue
            variants.append({
                "id": template.id,
                "code": template.code,
                "name": template.name,
                "is_active": template.is_active,
                "is_default": template.is_default,
                "published_version_id": latest_published.id,
                "published_version_number": latest_published.version_number,
            })
        return variants

    def get_flag_relationship_label(self, obj):
        relationship = obj.flag_relationship
        if relationship is None:
            return None
        organization_names = [
            organization.name
            for organization in (
                relationship.registry_organization,
                relationship.partner_organization,
            )
            if organization is not None
        ]
        return " / ".join([relationship.get_relationship_type_display(), *organization_names])


class OperationTemplateSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationTemplate
        fields = ["id", "name", "code", "description", "is_active", "is_default"]
