"""
Authorization services: capability sync, role provisioning, and the
policy functions that DRF permission classes call.
"""
from authorization.models import (
    Capability,
    RoleCapability,
    TenantRole,
    UserRoleAssignment,
)
from authorization.registry import (
    ALL_CAPABILITIES,
    CAPABILITY_REGISTRY,
    OPS_CAPABILITIES,
    VIEW_ONLY_CAPABILITIES,
)


# ---------------------------------------------------------------------------
# Capability synchronization (Stage 3)
# ---------------------------------------------------------------------------

def sync_capabilities() -> dict:
    """
    Idempotent: creates missing Capability rows, updates label/description/
    category/module_code on existing ones, and deactivates any DB rows whose
    code is no longer in the registry.

    Returns a summary dict for logging/management-command output.
    """
    registry_codes = set(CAPABILITY_REGISTRY.keys())
    existing = {c.code: c for c in Capability.objects.all()}
    created, updated, deactivated = 0, 0, 0

    for code, defn in CAPABILITY_REGISTRY.items():
        if code in existing:
            cap = existing[code]
            changed = False
            for attr in ("label", "description", "category", "module_code"):
                if getattr(cap, attr) != getattr(defn, attr):
                    setattr(cap, attr, getattr(defn, attr))
                    changed = True
            if not cap.is_active:
                cap.is_active = True
                cap.is_deprecated = False
                changed = True
            if changed:
                cap.save()
                updated += 1
        else:
            Capability.objects.create(
                code=code,
                label=defn.label,
                description=defn.description,
                category=defn.category,
                module_code=defn.module_code,
            )
            created += 1

    for code, cap in existing.items():
        if code not in registry_codes and cap.is_active:
            cap.is_active = False
            cap.is_deprecated = True
            cap.save()
            deactivated += 1

    return {"created": created, "updated": updated, "deactivated": deactivated}


# ---------------------------------------------------------------------------
# Default role templates (Stage 5)
# ---------------------------------------------------------------------------

_DEFAULT_ROLES = [
    {
        "name": "Tenant Admin",
        "description": "Full access to all platform capabilities.",
        "capabilities": ALL_CAPABILITIES,
    },
    {
        "name": "Operations",
        "description": "Day-to-day operations: manage service requests, documents, "
                       "workflow, and checklists. No rule/automation management.",
        "capabilities": OPS_CAPABILITIES,
    },
    {
        "name": "Viewer",
        "description": "Read-only access across all resources.",
        "capabilities": VIEW_ONLY_CAPABILITIES,
    },
]


def provision_default_roles(tenant) -> dict:
    """
    Idempotent: creates default TenantRole rows for a tenant if they
    don't already exist. Updates capability assignments on existing
    default roles to match the current registry.

    Returns a summary dict.
    """
    created_roles, updated_roles = 0, 0
    active_caps = {c.code: c for c in Capability.objects.filter(is_active=True)}

    for tmpl in _DEFAULT_ROLES:
        role, was_created = TenantRole.objects.get_or_create(
            tenant=tenant, name=tmpl["name"],
            defaults={
                "description": tmpl["description"],
                "is_system_default": True,
            },
        )
        if was_created:
            created_roles += 1
        else:
            updated_roles += 1

        desired_codes = tmpl["capabilities"] & set(active_caps.keys())
        current_codes = set(
            role.role_capabilities.values_list("capability__code", flat=True)
        )

        to_add = desired_codes - current_codes
        to_remove = current_codes - desired_codes

        if to_add:
            RoleCapability.objects.bulk_create([
                RoleCapability(role=role, capability=active_caps[code])
                for code in to_add
            ])
        if to_remove:
            role.role_capabilities.filter(capability__code__in=to_remove).delete()

    return {"created": created_roles, "updated": updated_roles}


# ---------------------------------------------------------------------------
# Cross-tenant validation (Stage 4)
# ---------------------------------------------------------------------------

class CrossTenantAssignmentError(Exception):
    pass


def assign_role(*, user, role: TenantRole) -> UserRoleAssignment:
    """
    Assign a role to a user with cross-tenant validation.
    Idempotent: returns existing assignment if already present.
    """
    if not user.tenant_id:
        raise CrossTenantAssignmentError("User has no tenant.")
    if user.tenant_id != role.tenant_id:
        raise CrossTenantAssignmentError(
            f"User tenant ({user.tenant_id}) does not match "
            f"role tenant ({role.tenant_id})."
        )
    assignment, _ = UserRoleAssignment.objects.get_or_create(user=user, role=role)
    return assignment


# ---------------------------------------------------------------------------
# Policy functions (Stage 6)
# ---------------------------------------------------------------------------

def user_effective_capabilities(user) -> frozenset[str]:
    """
    Returns the set of capability codes the user holds through all their
    active role assignments. Only active roles with active capabilities
    in the user's own tenant count.
    """
    if not getattr(user, "tenant_id", None):
        return frozenset()

    codes = (
        RoleCapability.objects
        .filter(
            role__user_assignments__user=user,
            role__tenant=user.tenant_id,
            role__is_active=True,
            capability__is_active=True,
        )
        .values_list("capability__code", flat=True)
        .distinct()
    )
    return frozenset(codes)


def user_has_capability(user, capability_code: str) -> bool:
    if not getattr(user, "tenant_id", None):
        return False

    return RoleCapability.objects.filter(
        role__user_assignments__user=user,
        role__tenant=user.tenant_id,
        role__is_active=True,
        capability__is_active=True,
        capability__code=capability_code,
    ).exists()
