from django import forms
from django.contrib import admin

from config.admin_utils import NoBulkDeleteMixin, ReadOnlyModelAdmin
from organizations.models import (
    Organization,
    ServiceRequestOrganization,
    TenantFlagRelationship,
)
from organizations.services import (
    CrossTenantReferenceError,
    FlagRelationshipValidationError,
    validate_flag_relationship,
)


class TenantFlagRelationshipForm(forms.ModelForm):
    class Meta:
        model = TenantFlagRelationship
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if "tenant" not in cleaned or "flag" not in cleaned:
            return cleaned
        try:
            validate_flag_relationship(
                tenant=cleaned["tenant"],
                flag=cleaned["flag"],
                registry_organization=cleaned.get("registry_organization"),
                partner_organization=cleaned.get("partner_organization"),
                status=cleaned.get("status"),
            )
        except (CrossTenantReferenceError, FlagRelationshipValidationError) as exc:
            raise forms.ValidationError(str(exc)) from exc
        if (
            self.instance.pk
            and self.instance.flag_id != cleaned["flag"].id
            and self.instance.service_offerings.exists()
        ):
            raise forms.ValidationError(
                "A relationship referenced by an offering cannot change its flag."
            )
        return cleaned


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "organization_type", "country", "updated_at")
    list_filter = ("tenant", "organization_type", "country")
    search_fields = ("name", "contact_email", "tenant__name")
    ordering = ("tenant__name", "name")
    raw_id_fields = ("tenant", "organization_type")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant", "organization_type")


@admin.register(TenantFlagRelationship)
class TenantFlagRelationshipAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    form = TenantFlagRelationshipForm
    list_display = (
        "tenant", "flag", "relationship_type", "partner_organization",
        "status", "valid_until",
    )
    list_filter = ("tenant", "relationship_type", "status", "flag")
    search_fields = (
        "tenant__name", "flag__name", "registry_organization__name",
        "partner_organization__name",
    )
    ordering = ("tenant__name", "flag__name", "relationship_type")
    raw_id_fields = (
        "tenant", "flag", "registry_organization", "partner_organization",
    )
    readonly_fields = ("created_at", "updated_at")
    list_select_related = (
        "tenant", "flag", "registry_organization", "partner_organization",
    )


@admin.register(ServiceRequestOrganization)
class ServiceRequestOrganizationAdmin(ReadOnlyModelAdmin):
    list_display = ("service_request", "tenant", "organization", "role")
    list_filter = ("tenant", "role")
    search_fields = (
        "service_request__reference_code", "organization__name", "tenant__name",
    )
    ordering = ("tenant__name", "service_request__reference_code")
    raw_id_fields = ("tenant", "service_request", "organization")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant", "service_request", "organization")
