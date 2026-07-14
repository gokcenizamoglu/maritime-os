"""
Shared test utilities for setting up RBAC in test fixtures.

Used by existing test suites that need their force_authenticate'd users
to pass capability checks introduced by the authorization sprint.
"""
from authorization.services import provision_default_roles, sync_capabilities


def grant_all_capabilities(user):
    """
    Sync capabilities, provision default roles for the user's tenant,
    and assign the user to "Tenant Admin" (which has all capabilities).
    Idempotent — safe to call in setUpTestData.
    """
    if not user.tenant_id:
        return

    from authorization.models import TenantRole, UserRoleAssignment

    sync_capabilities()
    provision_default_roles(user.tenant)
    admin_role = TenantRole.objects.get(tenant=user.tenant, name="Tenant Admin")
    UserRoleAssignment.objects.get_or_create(user=user, role=admin_role)
