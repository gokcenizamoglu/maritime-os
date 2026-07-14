"""
DRF permission class for capability-based authorization.

Used alongside IsTenantMember (which gates tenant membership) and
IsSameTenantObject (which gates cross-tenant object access). This class
adds the capability check on top of those existing guards.
"""
from authorization.services import user_has_capability
from rest_framework.permissions import BasePermission


class HasCapability(BasePermission):
    """
    Checks that the authenticated user holds a specific capability.

    Usage on a view:
        permission_classes = [IsTenantMember, HasCapability]
        capability_map = {
            "list": "service_request.view",
            "retrieve": "service_request.view",
            "create": "service_request.create",
        }

    Or for a single capability across all actions:
        required_capability = "activity.view"
    """
    message = "You do not have the required capability for this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        capability_map = getattr(view, "capability_map", None)
        if capability_map:
            action = getattr(view, "action", None)
            required = capability_map.get(action)
            if required is None:
                return True
            return user_has_capability(request.user, required)

        required = getattr(view, "required_capability", None)
        if required:
            return user_has_capability(request.user, required)

        return True
