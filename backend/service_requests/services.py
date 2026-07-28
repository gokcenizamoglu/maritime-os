"""
Service layer for ServiceRequest — the orchestration point that fans out
creation into checklist generation and workflow step instantiation, and
the ONLY path through which status transitions happen.
"""
from checklists.services import generate_checklist_for_service_request
from django.db import connection, transaction
from django.utils import timezone
from events.dispatcher import emit
from events.types import SERVICE_REQUEST_CREATED, SERVICE_REQUEST_STATUS_CHANGED
from catalog.models import TenantServiceOffering
from service_requests.models import ServiceRequest, ServiceRequestSequence
from service_requests.state_machine import assert_transition_allowed
from workflow.models import OperationTemplate, OperationTemplateVersion
from workflow.services import generate_workflow_steps_for_service_request


def _next_reference_code(tenant) -> str:
    """
    Allocate the next per-(tenant, year) sequence number with a SINGLE
    atomic upsert-and-increment statement:

        INSERT INTO <seq> (tenant_id, year, last_number) VALUES (%s, %s, 1)
        ON CONFLICT (tenant_id, year)
        DO UPDATE SET last_number = <seq>.last_number + 1
        RETURNING last_number

    WHY THIS SHAPE (vs. the previous select_for_update + Python `+= 1`):
      * ONE database operation. There is no read-into-Python /
        increment-in-Python / write-back window for a concurrent
        transaction to interleave into — the increment happens entirely
        inside the database, under the row lock Postgres takes on the
        conflicting row for the duration of the statement.
      * It does NOT depend on the row already existing, so it does not
        lean on get_or_create's implicit IntegrityError-recovery to
        bootstrap the first request of a (tenant, year). The INSERT
        branch handles "first ever"; the DO UPDATE branch handles "Nth" —
        both atomic, both serialized by the same unique index.
      * RETURNING hands back the exact post-increment value, sidestepping
        the F()-expression gotcha where the in-memory Python attribute is
        left stale after an UPDATE. We read the number the database
        actually committed for THIS statement, nothing else.

    MUST run inside the ServiceRequest-creating transaction (it does — see
    create_service_request's @transaction.atomic) so allocation and
    consumption are atomic: if that transaction rolls back, the increment
    rolls back with it (no gap); if it commits, the number is durably
    consumed exactly once.

    Postgres-specific (ON CONFLICT / RETURNING). The race-safety design
    already assumes Postgres row-lock semantics, so this adds no new
    backend assumption.
    """
    year = timezone.now().year
    seq = connection.ops.quote_name(ServiceRequestSequence._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {seq} (tenant_id, year, last_number) VALUES (%s, %s, 1) "
            f"ON CONFLICT (tenant_id, year) "
            f"DO UPDATE SET last_number = {seq}.last_number + 1 "
            f"RETURNING last_number",
            [tenant.id, year],
        )
        next_number = cursor.fetchone()[0]
    prefix = tenant.slug[:2].upper()
    return f"{prefix}-{year}-{next_number:04d}"


class CrossTenantReferenceError(Exception):
    """Raised when a related object does not belong to the acting tenant."""


class InvalidServiceRequestConfiguration(ValueError):
    """Raised when a catalog/template combination cannot open a new case."""


def _validate_offering(*, tenant, offering: TenantServiceOffering) -> None:
    if offering.tenant_id != tenant.id:
        raise CrossTenantReferenceError("Service offering does not belong to the acting tenant.")
    if not offering.service_type.is_active:
        raise InvalidServiceRequestConfiguration("The selected service type is inactive.")

    scope = offering.service_type.flag_scope
    has_flag = offering.flag_id is not None
    has_relationship = offering.flag_relationship_id is not None

    if scope == offering.service_type.FlagScope.REQUIRED and not (has_flag and has_relationship):
        raise InvalidServiceRequestConfiguration("This service requires an active flag relationship.")
    if scope == offering.service_type.FlagScope.NOT_APPLICABLE and (has_flag or has_relationship):
        raise InvalidServiceRequestConfiguration("This service cannot be associated with a flag.")
    if scope == offering.service_type.FlagScope.OPTIONAL and has_relationship != has_flag:
        raise InvalidServiceRequestConfiguration(
            "An optional flag context must include both a flag and its relationship, or neither."
        )
    if has_flag and not offering.flag.is_active:
        raise InvalidServiceRequestConfiguration("The selected flag is inactive.")

    if has_relationship:
        relationship = offering.flag_relationship
        if relationship.tenant_id != tenant.id or relationship.flag_id != offering.flag_id:
            raise CrossTenantReferenceError("The flag relationship is not valid for this offering.")
        if not relationship.is_available_for_new_requests():
            raise InvalidServiceRequestConfiguration("The flag relationship is inactive or expired.")
    elif has_flag:
        raise InvalidServiceRequestConfiguration("A flag-bound offering must reference a flag relationship.")

    if not offering.is_available_for_new_requests():
        raise InvalidServiceRequestConfiguration("The selected service offering is not accepting new requests.")


def _resolve_offering(*, tenant, service_offering, service_type, flag) -> TenantServiceOffering:
    if service_offering is not None:
        offering = (
            TenantServiceOffering.objects
            .select_related("service_type", "flag", "flag_relationship")
            .get(pk=service_offering.pk)
        )
        if offering.tenant_id != tenant.id:
            raise CrossTenantReferenceError("Service offering does not belong to the acting tenant.")
        if service_type is not None and offering.service_type_id != service_type.id:
            raise InvalidServiceRequestConfiguration("The service type does not match the selected offering.")
        if flag is not None and offering.flag_id != flag.id:
            raise InvalidServiceRequestConfiguration("The flag does not match the selected offering.")
    else:
        if service_type is None:
            raise InvalidServiceRequestConfiguration("service_offering is required for new requests.")
        queryset = TenantServiceOffering.objects.filter(
            tenant=tenant, service_type=service_type,
        ).select_related("service_type", "flag", "flag_relationship")
        queryset = queryset.filter(flag=flag) if flag is not None else queryset.filter(flag__isnull=True)
        candidates = [offering for offering in queryset if offering.is_available_for_new_requests()]
        if len(candidates) == 0:
            raise InvalidServiceRequestConfiguration(
                "No active service offering matches this legacy service_type + flag selection."
            )
        if len(candidates) > 1:
            raise InvalidServiceRequestConfiguration(
                "Multiple active offerings match this legacy selection; choose service_offering explicitly."
            )
        offering = candidates[0]

    _validate_offering(tenant=tenant, offering=offering)
    return offering


def _resolve_template(*, offering: TenantServiceOffering) -> tuple[OperationTemplate, OperationTemplateVersion]:
    template = (
        OperationTemplate.objects
        .filter(service_offering=offering, is_active=True, is_default=True)
        .first()
    )
    if template is None:
        raise InvalidServiceRequestConfiguration(
            "No active default operation template is configured for this offering."
        )

    version = (
        OperationTemplateVersion.objects
        .filter(operation_template=template, status=OperationTemplateVersion.Status.PUBLISHED)
        .order_by("-version_number")
        .first()
    )
    if version is None:
        raise InvalidServiceRequestConfiguration(
            "The selected operation template has no published version."
        )
    return template, version


@transaction.atomic
def create_service_request(
    *, tenant, customer, vessel, service_type=None, flag=None,
    service_offering=None, created_by,
) -> ServiceRequest:
    """
    Create a ServiceRequest and immediately instantiate its checklist and
    workflow steps from the matching templates. This is deliberate: a
    ServiceRequest without its checklist/workflow generated is an invalid
    intermediate state that should never be visible outside this
    transaction.

    Checklist/workflow generation are called directly here (not via
    events) because they are mandatory, synchronous parts of what
    "creating a ServiceRequest" MEANS — this function is the
    composition root for that invariant, not a place where downstream
    consequences should be free to opt in or out. Events are for
    genuinely optional/decoupled downstream reactions (logging,
    checklist recompute on document changes); the guarantee that every
    ServiceRequest has a checklist and workflow is not optional.
    """
    if customer.tenant_id != tenant.id:
        raise CrossTenantReferenceError(f"Customer {customer.id} does not belong to tenant {tenant.id}.")
    if vessel.tenant_id != tenant.id:
        raise CrossTenantReferenceError(f"Vessel {vessel.id} does not belong to tenant {tenant.id}.")
    if vessel.customer_id != customer.id:
        raise CrossTenantReferenceError(f"Vessel {vessel.id} does not belong to customer {customer.id}.")

    offering = _resolve_offering(
        tenant=tenant,
        service_offering=service_offering,
        service_type=service_type,
        flag=flag,
    )
    _, version = _resolve_template(offering=offering)

    service_request = ServiceRequest.objects.create(
        tenant=tenant,
        customer=customer,
        vessel=vessel,
        service_type=offering.service_type,
        flag=offering.flag,
        service_offering=offering,
        operation_template_version=version,
        created_by=created_by,
        reference_code=_next_reference_code(tenant),
        status=ServiceRequest.Status.DRAFT,
    )
    generate_checklist_for_service_request(service_request)
    generate_workflow_steps_for_service_request(service_request)

    emit(SERVICE_REQUEST_CREATED, service_request=service_request, actor_user=created_by)
    return service_request


@transaction.atomic
def transition_state(*, service_request: ServiceRequest, target_status: str, actor_user) -> ServiceRequest:
    """
    The ONLY sanctioned way to change ServiceRequest.status.

    ARCHITECTURAL CHANGE (state as a domain concept, not a free string):
    beyond validating the transition is on the allowed graph edge, this
    now also runs a GUARD — a domain rule about whether the ServiceRequest
    itself is actually ready to make that move (e.g. you cannot mark a
    case Completed while workflow steps are still open, regardless of
    what the state graph alone would permit). See
    `service_requests.state_machine.assert_transition_allowed` for the
    guard registry. This is what turns "status" from a label into an
    enforced domain invariant.
    """
    assert_transition_allowed(service_request, target_status)
    previous_status = service_request.status
    service_request.status = target_status
    service_request.save(update_fields=["status", "updated_at"])

    emit(
        SERVICE_REQUEST_STATUS_CHANGED,
        service_request=service_request,
        previous_status=previous_status,
        new_status=target_status,
        actor_user=actor_user,
    )
    return service_request
