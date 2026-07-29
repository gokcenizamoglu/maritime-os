from django.contrib import admin

from checklists.models import ChecklistItem
from config.admin_utils import ReadOnlyModelAdmin


@admin.register(ChecklistItem)
class ChecklistItemAdmin(ReadOnlyModelAdmin):
    list_display = (
        "service_request", "document_type", "required_count", "is_complete",
        "source_template", "updated_at",
    )
    list_filter = ("service_request__tenant", "is_complete", "document_type")
    search_fields = (
        "service_request__reference_code", "document_type__name",
        "source_template__code",
    )
    ordering = ("service_request__reference_code", "document_type__name")
    raw_id_fields = ("service_request", "document_type", "source_template")
    list_select_related = (
        "service_request", "service_request__tenant", "document_type", "source_template",
    )
