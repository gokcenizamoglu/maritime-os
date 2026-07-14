"""
Data migration: seed Capability rows, provision default roles for all
existing tenants, and map existing User.role values to the new RBAC
system.

Mapping:
  User.role="admin"  → TenantRole "Tenant Admin"  (all capabilities)
  User.role="ops"    → TenantRole "Operations"     (ops capabilities)
  User.role="viewer" → TenantRole "Viewer"         (view-only capabilities)

This migration is idempotent in logic: get_or_create prevents duplicates
on re-run. It is safe to run on an empty database (no-op) or on a
database with existing users.
"""
from django.db import migrations


def seed_forward(apps, schema_editor):
    from authorization.registry import (
        ALL_CAPABILITIES,
        CAPABILITY_REGISTRY,
        OPS_CAPABILITIES,
        VIEW_ONLY_CAPABILITIES,
    )

    Capability = apps.get_model("authorization", "Capability")
    TenantRole = apps.get_model("authorization", "TenantRole")
    RoleCapability = apps.get_model("authorization", "RoleCapability")
    UserRoleAssignment = apps.get_model("authorization", "UserRoleAssignment")
    Tenant = apps.get_model("tenants", "Tenant")
    User = apps.get_model("users", "User")

    # 1. Sync capabilities
    cap_objects = {}
    for code, defn in CAPABILITY_REGISTRY.items():
        cap, _ = Capability.objects.get_or_create(
            code=code,
            defaults={
                "label": defn.label,
                "description": defn.description,
                "category": defn.category,
                "module_code": defn.module_code,
            },
        )
        cap_objects[code] = cap

    # 2. Provision default roles for every existing tenant
    role_templates = [
        ("Tenant Admin", "Full access to all platform capabilities.", ALL_CAPABILITIES),
        ("Operations", "Day-to-day operations.", OPS_CAPABILITIES),
        ("Viewer", "Read-only access.", VIEW_ONLY_CAPABILITIES),
    ]

    role_map_per_tenant = {}
    for tenant in Tenant.objects.all():
        role_map_per_tenant[tenant.id] = {}
        for role_name, description, cap_codes in role_templates:
            role, _ = TenantRole.objects.get_or_create(
                tenant=tenant, name=role_name,
                defaults={
                    "description": description,
                    "is_system_default": True,
                },
            )
            role_map_per_tenant[tenant.id][role_name] = role
            active_codes = cap_codes & set(cap_objects.keys())
            existing_codes = set(
                RoleCapability.objects.filter(role=role).values_list(
                    "capability__code", flat=True,
                )
            )
            to_add = active_codes - existing_codes
            if to_add:
                RoleCapability.objects.bulk_create([
                    RoleCapability(role=role, capability=cap_objects[c])
                    for c in to_add
                ])

    # 3. Map existing User.role to UserRoleAssignment
    user_role_to_tenant_role = {
        "admin": "Tenant Admin",
        "ops": "Operations",
        "viewer": "Viewer",
    }

    for user in User.objects.filter(tenant__isnull=False).select_related("tenant"):
        tenant_roles = role_map_per_tenant.get(user.tenant_id, {})
        target_role_name = user_role_to_tenant_role.get(user.role)
        if target_role_name and target_role_name in tenant_roles:
            target_role = tenant_roles[target_role_name]
            UserRoleAssignment.objects.get_or_create(
                user=user, role=target_role,
            )


def seed_reverse(apps, schema_editor):
    UserRoleAssignment = apps.get_model("authorization", "UserRoleAssignment")
    RoleCapability = apps.get_model("authorization", "RoleCapability")
    TenantRole = apps.get_model("authorization", "TenantRole")
    Capability = apps.get_model("authorization", "Capability")

    UserRoleAssignment.objects.all().delete()
    RoleCapability.objects.all().delete()
    TenantRole.objects.all().delete()
    Capability.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0001_initial"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_reverse),
    ]
