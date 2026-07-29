from django.contrib import admin

from customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "contact_email", "contact_phone", "updated_at")
    list_filter = ("tenant",)
    search_fields = ("name", "contact_email", "contact_phone", "tenant__name")
    ordering = ("tenant__name", "name")
    raw_id_fields = ("tenant",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant",)
    date_hierarchy = "created_at"
