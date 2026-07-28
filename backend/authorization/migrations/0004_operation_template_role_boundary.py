from django.db import migrations


CATALOG_ADMIN_ONLY = {
    "tenant_catalog.manage",
    "operation_template.manage",
    "operation_template.publish",
}


def remove_catalog_admin_capabilities_from_operations(apps, schema_editor):
    TenantRole = apps.get_model("authorization", "TenantRole")
    RoleCapability = apps.get_model("authorization", "RoleCapability")
    RoleCapability.objects.filter(
        role__name="Operations",
        capability__code__in=CATALOG_ADMIN_ONLY,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("authorization", "0003_tenant_catalog_capabilities")]

    operations = [
        migrations.RunPython(remove_catalog_admin_capabilities_from_operations, migrations.RunPython.noop),
    ]
