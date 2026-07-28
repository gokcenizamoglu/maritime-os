from django.db import migrations


CAPABILITIES = {
    "customer.view": (
        "View Customers", "List and view customer details.",
        "customers", "core",
    ),
    "customer.create": (
        "Create Customers", "Create new customer records.",
        "customers", "core",
    ),
    "customer.update": (
        "Update Customers", "Edit existing customer records.",
        "customers", "core",
    ),
    "vessel.view": (
        "View Vessels", "List and view vessel details.",
        "vessels", "core",
    ),
    "vessel.create": (
        "Create Vessels", "Create new vessel records.",
        "vessels", "core",
    ),
    "vessel.update": (
        "Update Vessels", "Edit existing vessel records.",
        "vessels", "core",
    ),
}


def sync_customer_vessel_capabilities(apps, schema_editor):
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
    dependencies = [("authorization", "0004_operation_template_role_boundary")]

    operations = [migrations.RunPython(sync_customer_vessel_capabilities, migrations.RunPython.noop)]
