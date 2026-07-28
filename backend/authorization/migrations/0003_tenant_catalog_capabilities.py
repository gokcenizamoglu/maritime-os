from django.db import migrations


CAPABILITIES = {
    "tenant_catalog.view": (
        "View Tenant Catalog", "View tenant flag relationships and service offerings.",
        "tenant_catalog", "core",
    ),
    "tenant_catalog.manage": (
        "Manage Tenant Catalog", "Create and update tenant flag relationships and service offerings.",
        "tenant_catalog", "core",
    ),
    "operation_template.view": (
        "View Operation Templates", "View tenant operation templates, versions, and definitions.",
        "operation_templates", "core",
    ),
    "operation_template.manage": (
        "Manage Operation Templates", "Create and edit operation templates and draft definitions.",
        "operation_templates", "core",
    ),
    "operation_template.publish": (
        "Publish Operation Templates", "Publish, clone, and retire operation template versions.",
        "operation_templates", "core",
    ),
}


def sync_tenant_catalog_capabilities(apps, schema_editor):
    Capability = apps.get_model("authorization", "Capability")
    RoleCapability = apps.get_model("authorization", "RoleCapability")
    TenantRole = apps.get_model("authorization", "TenantRole")

    created = {}
    for code, (label, description, category, module_code) in CAPABILITIES.items():
        capability, _ = Capability.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "description": description,
                "category": category,
                "module_code": module_code,
                "is_active": True,
            },
        )
        created[code] = capability

    for role in TenantRole.objects.filter(name__in=["Tenant Admin", "Operations", "Viewer"]):
        if role.name == "Viewer":
            desired = {code for code in created if code.endswith(".view")}
        else:
            desired = set(created)
        for code in desired:
            RoleCapability.objects.get_or_create(role_id=role.id, capability_id=created[code].id)


class Migration(migrations.Migration):
    dependencies = [("authorization", "0002_seed_capabilities_and_roles")]

    operations = [migrations.RunPython(sync_tenant_catalog_capabilities, migrations.RunPython.noop)]
