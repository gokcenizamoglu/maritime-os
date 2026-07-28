"""
Minimum-viable permission classes shared across the authenticated API.

REVIEW FIX (#8): Phase 1 relied ENTIRELY on `get_queryset()` filtering
by tenant for isolation. That's necessary but not sufficient defense in
depth — it's easy for a future endpoint to add a `detail_route`/`@action`
that fetches an object some other way (e.g. `Model.objects.get(pk=...)`
directly, bypassing `get_queryset()`) and silently reintroduce
cross-tenant access. These classes make the tenant check an explicit,
reusable, testable unit instead of an implicit side effect of query
filtering.
"""
from rest_framework.permissions import BasePermission


class IsTenantMember(BasePermission):
    """
    Base requirement for ALL authenticated endpoints in this system:
    the user must be an internal staff member attached to a tenant.
    Rejects platform-level superusers with no tenant from hitting
    tenant-scoped business endpoints (they should use Django admin, not
    this API) and rejects any misconfigured account with tenant=None.
    """
    message = "This account is not associated with a tenant."

    def has_permission(self, request, view):
        tenant = getattr(request.user, "tenant", None)
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "tenant_id", None)
            and tenant is not None
            and tenant.is_active
        )


class IsSameTenantObject(BasePermission):
    """
    Object-level check: the object being accessed must belong to the
    requesting user's tenant. Apply this on top of `IsTenantMember` on
    any viewset whose `get_object()` could plausibly ever be reached by
    a path other than a tenant-filtered `get_queryset()` — i.e. treat it
    as a backstop, not a substitute for filtering.

    Assumes `obj` has a `.tenant_id` attribute directly OR via
    `.service_request.tenant_id` for nested objects — checked in that
    order.
    """
    message = "You do not have access to this object."

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "tenant_id"):
            return obj.tenant_id == request.user.tenant_id
        if hasattr(obj, "service_offering_id"):
            return obj.service_offering.tenant_id == request.user.tenant_id
        if hasattr(obj, "operation_template_id"):
            return obj.operation_template.service_offering.tenant_id == request.user.tenant_id
        if hasattr(obj, "operation_template_version_id"):
            return obj.operation_template_version.operation_template.service_offering.tenant_id == request.user.tenant_id
        if hasattr(obj, "service_request_id"):
            return obj.service_request.tenant_id == request.user.tenant_id
        return False
