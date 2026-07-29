from django.contrib import admin

from vessels.models import Vessel


@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = ("name", "imo_number", "tenant", "customer", "current_flag", "updated_at")
    list_filter = ("tenant", "current_flag", "vessel_type")
    search_fields = ("name", "imo_number", "customer__name", "tenant__name")
    ordering = ("tenant__name", "name")
    raw_id_fields = ("tenant", "customer", "current_flag")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("tenant", "customer", "current_flag")
    date_hierarchy = "created_at"
