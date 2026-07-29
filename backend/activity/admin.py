from django.contrib import admin

from activity.models import ActivityLog
from config.admin_utils import ReadOnlyModelAdmin


@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "created_at", "tenant", "verb", "entity_type", "entity_id",
        "actor_type", "actor_user", "service_request",
    )
    list_filter = ("tenant", "actor_type", "verb", "entity_type")
    search_fields = (
        "verb", "entity_type", "entity_id", "actor_user__username",
        "service_request__reference_code",
    )
    ordering = ("-created_at",)
    raw_id_fields = ("tenant", "service_request", "actor_user")
    list_select_related = ("tenant", "service_request", "actor_user")
    date_hierarchy = "created_at"
