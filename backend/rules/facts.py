"""
Fact resolution: turns a raw `events.dispatcher.DomainEvent` (whose
payload holds live model instances — a `Document`, a `ServiceRequest`,
...) into a flat `dict[str, str | None]` of primitive values a Rule's
`conditions` can compare against.

WHY THIS INDIRECTION EXISTS: a condition like `{"field": "service_type",
"value": "owner_change"}` needs to mean the SAME thing regardless of
which event triggered it — `DOCUMENT_CLASSIFIED` and
`WORKFLOW_STEP_STATUS_CHANGED` payloads don't share a shape, but both
have a `ServiceRequest` reachable from them, and both cases care about
"what ServiceType is this case". Each resolver below is responsible for
mapping ITS event's payload shape onto the same common vocabulary of
fact names, so `rules/conditions.py` never needs to know which event
produced the facts it's evaluating.

Adding support for a NEW event type is: (1) add the event name to
`events.types.RULE_TRIGGERABLE_EVENT_TYPES`, (2) add one resolver
function here, (3) register it in `FACT_RESOLVERS`, (4) list that
resolver's output keys in `EVENT_FACT_FIELDS` below (for the
`/api/rules/metadata/` read layer — see that dict's docstring for why
this one can't be derived automatically). Nothing else in this app
changes — this is the extensibility point requested for "more
conditions" later without touching the evaluator or the model.
"""
from typing import Any

from events.dispatcher import DomainEvent
from events.types import (
    CHECKLIST_ITEM_COMPLETION_CHANGED,
    DOCUMENT_CLASSIFIED,
    DOCUMENT_SUPERSEDED,
    DOCUMENT_UPLOADED,
    ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST,
    SERVICE_REQUEST_CREATED,
    SERVICE_REQUEST_STATUS_CHANGED,
    WORKFLOW_STEP_STATUS_CHANGED,
)


def _service_request_facts(service_request) -> dict[str, Any]:
    """Facts present on every event, since every event happens in the
    context of exactly one ServiceRequest."""
    return {
        "service_type": service_request.service_type.code,
        "flag": service_request.flag.code if service_request.flag else None,
        "service_request_status": service_request.status,
        "service_offering_id": service_request.service_offering_id,
        "operation_template_code": (
            service_request.operation_template_version.operation_template.code
            if service_request.operation_template_version_id else None
        ),
        "operation_template_version": (
            service_request.operation_template_version.version_number
            if service_request.operation_template_version_id else None
        ),
    }


def _resolve_document_uploaded(payload: dict) -> dict[str, Any]:
    return {
        **_service_request_facts(payload["service_request"]),
        "uploaded_by_type": payload["actor_type"],
    }


def _resolve_document_classified(payload: dict) -> dict[str, Any]:
    document = payload["document"]
    previous_type = payload.get("previous_document_type")
    return {
        **_service_request_facts(payload["service_request"]),
        "document_type": document.document_type.code if document.document_type else None,
        "previous_document_type": previous_type.code if previous_type else None,
    }


def _resolve_document_superseded(payload: dict) -> dict[str, Any]:
    new_document = payload["new_document"]
    return {
        **_service_request_facts(payload["service_request"]),
        "document_type": new_document.document_type.code if new_document.document_type else None,
    }


def _resolve_checklist_item_completion_changed(payload: dict) -> dict[str, Any]:
    checklist_item = payload["checklist_item"]
    return {
        **_service_request_facts(payload["service_request"]),
        "document_type": checklist_item.document_type.code,
        "is_complete": checklist_item.is_complete,
    }


def _resolve_service_request_created(payload: dict) -> dict[str, Any]:
    return _service_request_facts(payload["service_request"])


def _resolve_service_request_status_changed(payload: dict) -> dict[str, Any]:
    return {
        **_service_request_facts(payload["service_request"]),
        "previous_status": payload["previous_status"],
        "new_status": payload["new_status"],
    }


def _resolve_workflow_step_status_changed(payload: dict) -> dict[str, Any]:
    step_instance = payload["step_instance"]
    return {
        **_service_request_facts(step_instance.service_request),
        "step_code": step_instance.step_template.code,
        "previous_status": payload["previous_status"],
        "new_status": payload["new_status"],
    }


def _resolve_organization_attached(payload: dict) -> dict[str, Any]:
    link = payload["service_request_organization"]
    return {
        **_service_request_facts(payload["service_request"]),
        "organization_role": link.role,
        "organization_type": link.organization.organization_type.code,
    }


FACT_RESOLVERS = {
    DOCUMENT_UPLOADED: _resolve_document_uploaded,
    DOCUMENT_CLASSIFIED: _resolve_document_classified,
    DOCUMENT_SUPERSEDED: _resolve_document_superseded,
    CHECKLIST_ITEM_COMPLETION_CHANGED: _resolve_checklist_item_completion_changed,
    SERVICE_REQUEST_CREATED: _resolve_service_request_created,
    SERVICE_REQUEST_STATUS_CHANGED: _resolve_service_request_status_changed,
    WORKFLOW_STEP_STATUS_CHANGED: _resolve_workflow_step_status_changed,
    ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST: _resolve_organization_attached,
}


_COMMON_FACT_FIELDS = [
    "service_type", "flag", "service_request_status", "service_offering_id",
    "operation_template_code", "operation_template_version",
]

# Field names each resolver above puts into its facts dict — used ONLY
# by the read-only /api/rules/metadata/ endpoint (rules/views.py) so a
# rule-builder UI can list "available facts" for a chosen event without
# fabricating a fake event and actually running a resolver against it
# (resolvers expect live model instances in the payload — a document, a
# service_request — which don't exist outside a real event). This is
# necessarily a second, static listing of what each resolver ABOVE
# returns; keep it in sync by hand when a resolver's returned keys
# change (see the module docstring's 4-step "adding a new event type"
# checklist). It is not consulted by evaluate_conditions() or any other
# runtime path — only by the metadata endpoint.
EVENT_FACT_FIELDS: dict[str, list[str]] = {
    DOCUMENT_UPLOADED: [*_COMMON_FACT_FIELDS, "uploaded_by_type"],
    DOCUMENT_CLASSIFIED: [*_COMMON_FACT_FIELDS, "document_type", "previous_document_type"],
    DOCUMENT_SUPERSEDED: [*_COMMON_FACT_FIELDS, "document_type"],
    CHECKLIST_ITEM_COMPLETION_CHANGED: [*_COMMON_FACT_FIELDS, "document_type", "is_complete"],
    SERVICE_REQUEST_CREATED: [*_COMMON_FACT_FIELDS],
    SERVICE_REQUEST_STATUS_CHANGED: [*_COMMON_FACT_FIELDS, "previous_status", "new_status"],
    WORKFLOW_STEP_STATUS_CHANGED: [*_COMMON_FACT_FIELDS, "step_code", "previous_status", "new_status"],
    ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST: [*_COMMON_FACT_FIELDS, "organization_role", "organization_type"],
}


def resolve_service_request(event: DomainEvent):
    """
    Every event a Rule can trigger on happens in the context of exactly
    one ServiceRequest — this finds it regardless of which payload shape
    the event uses, since actions need a ServiceRequest to act on.
    """
    payload = event.payload
    if "service_request" in payload:
        return payload["service_request"]
    if "step_instance" in payload:
        return payload["step_instance"].service_request
    return None


def resolve_facts(event: DomainEvent) -> dict[str, Any]:
    resolver = FACT_RESOLVERS.get(event.name)
    if resolver is None:
        return {}
    return resolver(event.payload)
