"""
Service layer for the checklist domain.

Two responsibilities live here, and ONLY here:
  1. Instantiating ChecklistItems from ChecklistTemplates when a
     ServiceRequest is created (or re-scoped).
  2. Recomputing a ChecklistItem's derived `is_complete` cache whenever
     the underlying Document mappings change.

No view, serializer, or signal handler should touch ChecklistItem.is_complete
directly — everything routes through recompute_checklist_item() so there is
exactly one place that defines what "complete" means.
"""
from checklists.models import ChecklistItem, ChecklistTemplate
from django.db import transaction
from service_requests.models import ServiceRequest
from workflow.models import OperationTemplateVersion


class ChecklistDefinitionValidationError(ValueError):
    pass


@transaction.atomic
def save_checklist_definition(*, tenant, data, instance=None):
    from checklists.models import ChecklistTemplate

    version = data.get(
        "operation_template_version", instance.operation_template_version if instance else None,
    )
    if version is None:
        raise ChecklistDefinitionValidationError("operation_template_version is required.")
    if version.operation_template.service_offering.tenant_id != tenant.id:
        raise ChecklistDefinitionValidationError("Version does not belong to the acting tenant.")
    if version.status != OperationTemplateVersion.Status.DRAFT:
        raise ChecklistDefinitionValidationError("Only draft versions can be edited.")
    if instance is None:
        return ChecklistTemplate.objects.create(**data)
    if instance.operation_template_version_id != version.id:
        raise ChecklistDefinitionValidationError("A checklist definition cannot move between versions.")
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    return instance


def generate_checklist_for_service_request(service_request: ServiceRequest) -> list[ChecklistItem]:
    """
    Instantiate ChecklistItems from the immutable published version linked
    to the ServiceRequest. The legacy service/flag lookup remains only for
    historical rows that have not yet been backfilled; new requests cannot
    enter that path.
    """
    if service_request.operation_template_version_id:
        templates = ChecklistTemplate.objects.filter(
            operation_template_version_id=service_request.operation_template_version_id,
            is_active=True,
        ).select_related("document_type")
    else:
        templates = ChecklistTemplate.objects.filter(
            service_type=service_request.service_type,
            flag=service_request.flag,
            is_active=True,
        ).select_related("document_type")

    created_items = []
    with transaction.atomic():
        for template in templates:
            item, _ = ChecklistItem.objects.get_or_create(
                service_request=service_request,
                document_type=template.document_type,
                defaults={
                    "required_count": template.min_count,
                    "source_template": template,
                },
            )
            if item.source_template_id != template.id:
                item.source_template = template
                item.required_count = template.min_count
                item.save(update_fields=["source_template", "required_count", "updated_at"])
            created_items.append(item)
    return created_items


def recompute_checklist_item(checklist_item: ChecklistItem) -> ChecklistItem:
    """
    The single source of truth for "is this checklist item complete".

    Complete = at least `required_count` non-superseded Documents exist
    for this ServiceRequest, mapped to this DocumentType, with status in
    {classified, validated}. Explicitly does NOT count `unclassified`
    documents — an uploaded-but-unmapped file does not satisfy a
    requirement.

    Call this after ANY change that could affect the answer: a document
    is classified/reclassified, unmapped, superseded, or deleted.
    """
    # Import here to avoid a circular import at module load time
    # (documents imports checklists.models for the FK).
    from documents.models import Document

    qualifying_count = Document.objects.filter(
        service_request=checklist_item.service_request,
        document_type=checklist_item.document_type,
        status__in=[Document.Status.CLASSIFIED, Document.Status.VALIDATED],
        superseded_by_set__isnull=True,  # exclude documents that have since been superseded
    ).count()

    is_complete = qualifying_count >= checklist_item.required_count
    if is_complete != checklist_item.is_complete:
        checklist_item.is_complete = is_complete
        checklist_item.save(update_fields=["is_complete", "updated_at"])

        # ARCHITECTURAL CHANGE: previously called activity.services.log_activity
        # directly. Now emits a domain event instead — the checklist
        # domain no longer needs to import or know about the activity
        # domain at all. See activity/listeners.py for the logging
        # consumer of this event.
        from events.dispatcher import emit
        from events.types import CHECKLIST_ITEM_COMPLETION_CHANGED
        emit(
            CHECKLIST_ITEM_COMPLETION_CHANGED,
            checklist_item=checklist_item,
            service_request=checklist_item.service_request,
            is_complete=is_complete,
        )
    return checklist_item


def get_checklist_progress(service_request: ServiceRequest) -> dict:
    """Convenience summary for API responses / UI progress bars."""
    items = list(service_request.checklist_items.all())
    total = len(items)
    complete = sum(1 for i in items if i.is_complete)
    return {
        "total": total,
        "complete": complete,
        "percent": round((complete / total) * 100, 1) if total else 0.0,
        "items": items,
    }
