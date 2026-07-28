from django.db import migrations, transaction
from django.utils import timezone


def backfill_historical_operations(apps, schema_editor):
    """Bind existing cases without opening unverified catalog access.

    A ServiceRequest is evidence that a tenant used a service/flag pair in
    the past. It is not evidence that every tenant can use every global
    catalog combination, so this migration only creates rows for existing
    operations. Backfilled rows are inactive and cannot accept new work.
    """
    TenantFlagRelationship = apps.get_model("organizations", "TenantFlagRelationship")
    TenantServiceOffering = apps.get_model("catalog", "TenantServiceOffering")
    OperationTemplate = apps.get_model("workflow", "OperationTemplate")
    OperationTemplateVersion = apps.get_model("workflow", "OperationTemplateVersion")
    LegacyChecklistTemplate = apps.get_model("checklists", "ChecklistTemplate")
    ChecklistItem = apps.get_model("checklists", "ChecklistItem")
    LegacyWorkflowTemplate = apps.get_model("workflow", "WorkflowStepTemplate")
    WorkflowStepInstance = apps.get_model("workflow", "WorkflowStepInstance")
    ServiceRequest = apps.get_model("service_requests", "ServiceRequest")

    with transaction.atomic():
        for service_request in ServiceRequest.objects.select_related(
            "tenant", "service_type", "flag",
        ).all():
            if not service_request.flag_id:
                continue

            relationship, relationship_created = TenantFlagRelationship.objects.get_or_create(
                tenant_id=service_request.tenant_id,
                flag_id=service_request.flag_id,
                relationship_type="direct",
                registry_organization_id=None,
                partner_organization_id=None,
                defaults={
                    "status": "inactive",
                    "notes": "Backfilled from historical ServiceRequest data; current availability was not inferred.",
                },
            )
            if relationship_created:
                relationship.save()

            offering, _ = TenantServiceOffering.objects.get_or_create(
                tenant_id=service_request.tenant_id,
                service_type_id=service_request.service_type_id,
                flag_relationship_id=relationship.id,
                defaults={
                    "flag_id": service_request.flag_id,
                    "display_name": service_request.service_type.name,
                    "status": "inactive",
                    "accepts_new_requests": False,
                    "description": "Backfilled from historical ServiceRequest data; current availability was not inferred.",
                },
            )

            template, _ = OperationTemplate.objects.get_or_create(
                service_offering_id=offering.id,
                code=f"legacy-{service_request.service_type.code}-{service_request.flag.code}"[:80],
                defaults={
                    "name": f"Legacy {service_request.service_type.name} / {service_request.flag.name}",
                    "description": "Historical process recipe migrated from global templates.",
                    "is_active": False,
                    "is_default": False,
                },
            )
            version, _ = OperationTemplateVersion.objects.get_or_create(
                operation_template_id=template.id,
                version_number=1,
                defaults={
                    "status": "published",
                    "published_at": timezone.now(),
                },
            )
            if version.status != "published":
                version.status = "published"
                version.published_at = version.published_at or timezone.now()
                version.save(update_fields=["status", "published_at"])

            checklist_by_document_type = {}
            for legacy in LegacyChecklistTemplate.objects.filter(
                service_type_id=service_request.service_type_id,
                flag_id=service_request.flag_id,
                is_active=True,
            ):
                code = legacy.code or f"document-{legacy.document_type_id}"
                copied, _ = LegacyChecklistTemplate.objects.get_or_create(
                    operation_template_version_id=version.id,
                    document_type_id=legacy.document_type_id,
                    defaults={
                        "code": code[:80],
                        "min_count": legacy.min_count,
                        "is_active": legacy.is_active,
                    },
                )
                checklist_by_document_type[legacy.document_type_id] = copied

            legacy_steps = list(LegacyWorkflowTemplate.objects.filter(
                service_type_id=service_request.service_type_id,
            ).filter(
                flag_id=service_request.flag_id,
            ))
            legacy_flagless_steps = list(LegacyWorkflowTemplate.objects.filter(
                service_type_id=service_request.service_type_id,
                flag_id=None,
            ))
            selected_by_code = {}
            for legacy_step in legacy_steps + legacy_flagless_steps:
                selected_by_code.setdefault(legacy_step.code, legacy_step)

            copied_by_code = {}
            for legacy_step in selected_by_code.values():
                copied, _ = LegacyWorkflowTemplate.objects.get_or_create(
                    operation_template_version_id=version.id,
                    code=legacy_step.code,
                    defaults={
                        "name": legacy_step.name,
                        "is_external": legacy_step.is_external,
                        "responsible_organization_type_id": legacy_step.responsible_organization_type_id,
                    },
                )
                copied_by_code[legacy_step.code] = copied
            for legacy_step in selected_by_code.values():
                copied = copied_by_code[legacy_step.code]
                dependencies = [
                    copied_by_code[dependency.code]
                    for dependency in legacy_step.depends_on.all()
                    if dependency.code in copied_by_code
                ]
                copied.depends_on.set(dependencies)

            for item in ChecklistItem.objects.filter(service_request_id=service_request.id):
                source = checklist_by_document_type.get(item.document_type_id)
                if source and item.source_template_id != source.id:
                    item.source_template_id = source.id
                    item.save(update_fields=["source_template"])

            for instance in WorkflowStepInstance.objects.filter(
                service_request_id=service_request.id,
            ).select_related("step_template"):
                replacement = copied_by_code.get(instance.step_template.code)
                if replacement and instance.step_template_id != replacement.id:
                    instance.step_template_id = replacement.id
                    instance.save(update_fields=["step_template"])

            service_request.service_offering_id = offering.id
            service_request.operation_template_version_id = version.id
            service_request.save(update_fields=["service_offering", "operation_template_version"])


class Migration(migrations.Migration):
    dependencies = [
        ("service_requests", "0003_servicerequest_operation_template_version_and_more"),
        ("catalog", "0003_tenantserviceoffering_flag_relationship_and_more"),
        ("organizations", "0003_tenantflagrelationship"),
        ("checklists", "0003_checklistitem_source_template_checklisttemplate_code_and_more"),
        ("workflow", "0002_alter_workflowsteptemplate_service_type_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_historical_operations, migrations.RunPython.noop),
    ]
