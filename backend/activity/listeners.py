"""
The activity/timeline domain's event handlers.

ARCHITECTURAL CHANGE: previously every service function
(`upload_document`, `classify_document`, `transition_state`,
`update_step_status`, `recompute_checklist_item`, ...) called
`activity.services.log_activity(...)` directly, inline, with its own
ad-hoc metadata shape. That meant "what does this event look like in
the audit trail" was a decision scattered across five files.

Now it's centralized here: one handler per domain event, each building
a clean, human-readable `summary` plus structured `metadata`. Adding a
NEW event elsewhere in the system means adding ONE handler here — the
emitting code doesn't change, and doesn't need to know logging exists.
"""
from activity.services import log_activity
from events.dispatcher import on
from events.types import (
    CHECKLIST_ITEM_COMPLETION_CHANGED,
    DOCUMENT_CLASSIFIED,
    DOCUMENT_SUPERSEDED,
    DOCUMENT_UPLOADED,
    ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST,
    RULE_ACTION_FAILED,
    SERVICE_REQUEST_CREATED,
    SERVICE_REQUEST_STATUS_CHANGED,
    WORKFLOW_STEP_STATUS_CHANGED,
)


@on(DOCUMENT_UPLOADED)
def _log_document_uploaded(event):
    document = event.payload["document"]
    log_activity(
        tenant=document.tenant,
        verb=DOCUMENT_UPLOADED,
        entity_type="document",
        entity_id=document.id,
        service_request=event.payload["service_request"],
        actor_type=event.payload["actor_type"],
        actor_user=event.payload.get("actor_user"),
        summary=f'"{document.original_filename}" uploaded by {event.payload["actor_type"]}',
        metadata={"filename": document.original_filename},
    )


@on(DOCUMENT_CLASSIFIED)
def _log_document_classified(event):
    document = event.payload["document"]
    previous_type = event.payload.get("previous_document_type")
    summary = (
        f'Reclassified "{document.original_filename}" from {previous_type.name} to {document.document_type.name}'
        if previous_type and previous_type.id != document.document_type.id
        else f'"{document.original_filename}" classified as {document.document_type.name}'
    )
    log_activity(
        tenant=document.tenant,
        verb=DOCUMENT_CLASSIFIED,
        entity_type="document",
        entity_id=document.id,
        service_request=event.payload["service_request"],
        actor_type=event.payload["actor_type"],
        actor_user=event.payload.get("actor_user"),
        summary=summary,
        metadata={
            "document_type": document.document_type.code,
            "previous_document_type": previous_type.code if previous_type else None,
            "status": document.status,
        },
    )


@on(DOCUMENT_SUPERSEDED)
def _log_document_superseded(event):
    new_document = event.payload["new_document"]
    log_activity(
        tenant=new_document.tenant,
        verb=DOCUMENT_SUPERSEDED,
        entity_type="document",
        entity_id=new_document.id,
        service_request=event.payload["service_request"],
        actor_type=event.payload["actor_type"],
        actor_user=event.payload.get("actor_user"),
        summary=f'"{event.payload["old_document"].original_filename}" replaced with a corrected version',
        metadata={"supersedes": event.payload["old_document"].id},
    )


@on(CHECKLIST_ITEM_COMPLETION_CHANGED)
def _log_checklist_completion_changed(event):
    checklist_item = event.payload["checklist_item"]
    is_complete = event.payload["is_complete"]
    log_activity(
        tenant=checklist_item.service_request.tenant,
        verb=CHECKLIST_ITEM_COMPLETION_CHANGED,
        entity_type="checklist_item",
        entity_id=checklist_item.id,
        service_request=checklist_item.service_request,
        actor_type="system",
        summary=f"{checklist_item.document_type.name} checklist item marked "
                f"{'complete' if is_complete else 'incomplete'}",
        metadata={"document_type": checklist_item.document_type.code, "is_complete": is_complete},
    )


@on(SERVICE_REQUEST_CREATED)
def _log_service_request_created(event):
    service_request = event.payload["service_request"]
    log_activity(
        tenant=service_request.tenant,
        verb=SERVICE_REQUEST_CREATED,
        entity_type="service_request",
        entity_id=service_request.id,
        service_request=service_request,
        actor_type="user",
        actor_user=event.payload.get("actor_user"),
        summary=f"Case {service_request.reference_code} created "
                f"({service_request.service_type.name} / {service_request.flag.name})",
    )


@on(SERVICE_REQUEST_STATUS_CHANGED)
def _log_service_request_status_changed(event):
    service_request = event.payload["service_request"]
    log_activity(
        tenant=service_request.tenant,
        verb=SERVICE_REQUEST_STATUS_CHANGED,
        entity_type="service_request",
        entity_id=service_request.id,
        service_request=service_request,
        actor_type="user" if event.payload.get("actor_user") else "system",
        actor_user=event.payload.get("actor_user"),
        summary=f'Status changed from "{event.payload["previous_status"]}" to "{event.payload["new_status"]}"',
        metadata={"from": event.payload["previous_status"], "to": event.payload["new_status"]},
    )


@on(WORKFLOW_STEP_STATUS_CHANGED)
def _log_workflow_step_status_changed(event):
    step_instance = event.payload["step_instance"]
    log_activity(
        tenant=step_instance.service_request.tenant,
        verb=WORKFLOW_STEP_STATUS_CHANGED,
        entity_type="workflow_step_instance",
        entity_id=step_instance.id,
        service_request=step_instance.service_request,
        actor_type="user" if event.payload.get("actor_user") else "system",
        actor_user=event.payload.get("actor_user"),
        summary=f"{step_instance.step_template.name}: {event.payload['new_status']}",
        metadata={"step": step_instance.step_template.code, "status": event.payload["new_status"]},
    )


@on(ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST)
def _log_organization_attached(event):
    link = event.payload["service_request_organization"]
    log_activity(
        tenant=link.tenant,
        verb=ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST,
        entity_type="service_request_organization",
        entity_id=link.id,
        service_request=event.payload["service_request"],
        actor_type="user" if event.payload.get("actor_user") else "system",
        actor_user=event.payload.get("actor_user"),
        summary=f"{link.organization.name} attached as {link.get_role_display()}",
        metadata={"organization": link.organization.name, "role": link.role},
    )


@on(RULE_ACTION_FAILED)
def _log_rule_action_failed(event):
    """
    RULE_ACTION_EXECUTED is deliberately NOT logged here — a rule that
    successfully calls, say, `transition_state()` already gets a
    `service_request.status_changed` timeline entry from that action's
    own event, via the handler above. Logging RULE_ACTION_EXECUTED too
    would put two entries on the timeline for one real-world consequence.
    A FAILED rule, by contrast, produces no other event at all (the
    action's own service function never emitted anything, since it
    raised) — so this is the only place that failure becomes visible to
    an operator looking at the case timeline, rather than only living in
    `RuleExecutionLog` where nobody but an engineer would think to look.
    """
    rule = event.payload["rule"]
    log_activity(
        tenant=rule.tenant,
        verb=RULE_ACTION_FAILED,
        entity_type="rule",
        entity_id=rule.id,
        service_request=event.payload["service_request"],
        actor_type="system",
        summary=f"Automation rule '{rule.name}' failed to run: {event.payload['error']}",
        metadata={"rule_id": rule.id, "action_type": rule.action_type, "error": event.payload["error"]},
    )
