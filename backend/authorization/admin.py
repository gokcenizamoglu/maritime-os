from django.contrib import admin

from authorization.models import (
    Capability,
    RoleCapability,
    TenantRole,
    UserRoleAssignment,
)
from config.admin_utils import NoBulkDeleteMixin


@admin.register(Capability)
class CapabilityAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    list_display = (
        "code", "label", "category", "module_code", "is_active", "is_deprecated",
    )
    list_filter = ("category", "module_code", "is_active", "is_deprecated")
    search_fields = ("code", "label", "description")
    ordering = ("code",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TenantRole)
class TenantRoleAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "tenant", "is_system_default", "is_active", "updated_at")
    list_filter = ("tenant", "is_system_default", "is_active")
    search_fields = ("name", "description", "tenant__name")
    ordering = ("tenant__name", "name")
    raw_id_fields = ("tenant",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant",)


@admin.register(RoleCapability)
class RoleCapabilityAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    list_display = ("role", "tenant", "capability", "created_at")
    list_filter = ("role__tenant", "capability__category")
    search_fields = ("role__name", "role__tenant__name", "capability__code")
    ordering = ("role__tenant__name", "role__name", "capability__code")
    raw_id_fields = ("role", "capability")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("role", "role__tenant", "capability")

    @admin.display(ordering="role__tenant", description="Tenant")
    def tenant(self, obj):
        return obj.role.tenant


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("role__tenant", "role")
    search_fields = ("user__username", "user__email", "role__name", "role__tenant__name")
    ordering = ("role__tenant__name", "user__username")
    raw_id_fields = ("user", "role")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("user", "role", "role__tenant")

    @admin.display(ordering="role__tenant", description="Tenant")
    def tenant(self, obj):
        return obj.role.tenant
