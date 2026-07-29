from django import forms
from django.contrib import admin

from catalog.models import (
    DocumentType,
    Flag,
    OrganizationType,
    ServiceType,
    TenantServiceOffering,
)
from config.admin_utils import NoBulkDeleteMixin
from catalog.services import OfferingValidationError, validate_offering_configuration


class TenantServiceOfferingForm(forms.ModelForm):
    class Meta:
        model = TenantServiceOffering
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        required = ("tenant", "service_type")
        if any(field not in cleaned for field in required):
            return cleaned
        try:
            validate_offering_configuration(
                tenant=cleaned["tenant"],
                service_type=cleaned["service_type"],
                flag=cleaned.get("flag"),
                flag_relationship=cleaned.get("flag_relationship"),
                status=cleaned.get("status"),
                valid_from=cleaned.get("valid_from"),
                valid_until=cleaned.get("valid_until"),
            )
        except OfferingValidationError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "flag_scope", "is_active")
    list_filter = ("flag_scope", "is_active")
    search_fields = ("name", "code", "description")
    ordering = ("name",)


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_global", "is_active")
    list_filter = ("is_global", "is_active")
    search_fields = ("name", "code", "description")
    ordering = ("name",)


@admin.register(OrganizationType)
class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(TenantServiceOffering)
class TenantServiceOfferingAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    form = TenantServiceOfferingForm
    list_display = (
        "display_label", "tenant", "service_type", "flag", "status",
        "accepts_new_requests", "valid_until",
    )
    list_filter = ("tenant", "status", "accepts_new_requests", "service_type", "flag")
    search_fields = (
        "display_name", "service_type__name", "flag__name", "tenant__name",
        "flag_relationship__partner_organization__name",
    )
    ordering = ("tenant__name", "service_type__name", "flag__name", "id")
    raw_id_fields = (
        "tenant", "service_type", "flag", "flag_relationship",
    )
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant", "service_type", "flag", "flag_relationship")
    date_hierarchy = "created_at"

    @admin.display(description="Offering")
    def display_label(self, obj):
        return str(obj)
