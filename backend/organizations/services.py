"""
Service layer for the collaboration domain.

Previously `ServiceRequestOrganization` rows could be created with ANY
role/organization pairing — nothing stopped attaching a law firm with
role=FLAG_AUTHORITY. The unique constraint on
(service_request, organization, role) already allows the SAME
organization to hold multiple different roles, and allows MULTIPLE
organizations to hold the same role on one case (two law firms, say) —
that flexibility was already correct and is preserved. What was
missing was role/type CONSISTENCY: the role claimed should match what
kind of organization is actually capable of holding it.
"""
from django.db import transaction
from events.dispatcher import emit
from events.types import ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST
from organizations.models import Organization, ServiceRequestOrganization
from service_requests.models import ServiceRequest

# Maps a ServiceRequestOrganization role to the OrganizationType code(s)
# allowed to hold it. `OTHER` intentionally allows any type — it exists
# precisely for roles that don't fit the common categories.
ROLE_ALLOWED_ORGANIZATION_TYPE_CODES = {
    ServiceRequestOrganization.Role.HANDLING_LAWYER: {"law_firm"},
    ServiceRequestOrganization.Role.FLAG_AUTHORITY: {"flag_authority"},
    ServiceRequestOrganization.Role.PNI_CLUB: {"pni_club"},
    ServiceRequestOrganization.Role.CLASS_SOCIETY: {"class_society"},
}


class RoleOrganizationTypeMismatchError(Exception):
    pass


class CrossTenantReferenceError(Exception):
    pass


@transaction.atomic
def attach_organization_to_service_request(
    *, service_request: ServiceRequest, organization: Organization, role: str, actor_user=None,
) -> ServiceRequestOrganization:
    """
    Attach an external organization to a ServiceRequest in a given role.
    Idempotent on (service_request, organization, role) via
    get_or_create, matching the existing unique constraint.

    Enforces two invariants that previously had nothing checking them:
      1. The organization must belong to the SAME tenant as the
         ServiceRequest (cross-tenant org attachment would let one
         tenant's case reference another tenant's law firm contact).
      2. The organization's `organization_type` must be an allowed type
         for the claimed role (see ROLE_ALLOWED_ORGANIZATION_TYPE_CODES),
         unless role is OTHER.
    """
    if organization.tenant_id != service_request.tenant_id:
        raise CrossTenantReferenceError(
            f"Organization {organization.id} does not belong to the same tenant as "
            f"ServiceRequest {service_request.id}."
        )

    allowed_type_codes = ROLE_ALLOWED_ORGANIZATION_TYPE_CODES.get(role)
    if allowed_type_codes and organization.organization_type.code not in allowed_type_codes:
        raise RoleOrganizationTypeMismatchError(
            f"Organization '{organization.name}' has type "
            f"'{organization.organization_type.code}', which cannot hold role "
            f"'{role}' (expected one of {sorted(allowed_type_codes)})."
        )

    link, created = ServiceRequestOrganization.objects.get_or_create(
        tenant=service_request.tenant,
        service_request=service_request,
        organization=organization,
        role=role,
    )
    if created:
        emit(
            ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST,
            service_request_organization=link,
            service_request=service_request,
            actor_user=actor_user,
        )
    return link
