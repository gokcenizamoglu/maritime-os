from django.contrib import admin

from checklists.models import ChecklistItem
from config.admin_utils import ReadOnlyModelAdmin, ReadOnlyTabularInline
from service_requests.models import ServiceRequest
from workflow.models import WorkflowStepInstance


class ChecklistItemInline(ReadOnlyTabularInline):
    model = ChecklistItem
    fields = (
        "document_type", "source_template", "required_count", "is_complete",
        "created_at", "updated_at",
    )
    raw_id_fields = ("document_type", "source_template")


class WorkflowStepInstanceInline(ReadOnlyTabularInline):
    model = WorkflowStepInstance
    fields = (
        "step_template", "status", "assigned_organization", "started_at", "completed_at",
    )
    raw_id_fields = ("step_template", "assigned_organization")


@admin.register(ServiceRequest)
class ServiceRequestAdmin(ReadOnlyModelAdmin):
    inlines = (ChecklistItemInline, WorkflowStepInstanceInline)
    list_display = (
        "reference_code", "tenant", "customer", "vessel", "service_type",
        "flag", "status", "created_by", "created_at",
    )
    list_filter = ("tenant", "status", "service_type", "flag")
    search_fields = (
        "reference_code", "customer__name", "vessel__name", "vessel__imo_number",
        "tenant__name",
    )
    ordering = ("-created_at",)
    raw_id_fields = (
        "tenant", "customer", "vessel", "service_type", "flag",
        "service_offering", "operation_template_version", "created_by",
    )
    list_select_related = (
        "tenant", "customer", "vessel", "service_type", "flag",
        "service_offering", "operation_template_version", "created_by",
    )
    date_hierarchy = "created_at"
