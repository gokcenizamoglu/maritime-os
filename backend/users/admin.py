from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from users.models import User


@admin.register(User)
class MaritimeUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("MaritimeOS access", {"fields": ("tenant", "role")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("MaritimeOS access", {"fields": ("tenant", "role")}),
    )
    list_display = (
        "username", "email", "tenant", "role", "is_staff", "is_superuser", "is_active",
    )
    list_filter = ("tenant", "role", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "tenant__name")
    ordering = ("username",)
    raw_id_fields = ("tenant",)
