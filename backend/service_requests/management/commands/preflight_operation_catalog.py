from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.recorder import MigrationRecorder

from catalog.models import ServiceType, TenantServiceOffering
from checklists.models import ChecklistTemplate
from organizations.models import Organization, TenantFlagRelationship
from service_requests.models import ServiceRequest
from workflow.models import OperationTemplate, OperationTemplateVersion, WorkflowStepTemplate


MIGRATION_NAME = "0004_backfill_operation_catalog"


class Command(BaseCommand):
    help = "Read-only validation gate for the tenant catalog backfill and versioned templates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-ids", type=int, default=20,
            help="Maximum offending IDs printed for each category (default: 20).",
        )
        parser.add_argument(
            "--large-data-threshold", type=int, default=10000,
            help="Flag a flagged ServiceRequest population above this count (default: 10000).",
        )

    def handle(self, *args, **options):
        self.max_ids = max(options["max_ids"], 1)
        self.large_data_threshold = max(options["large_data_threshold"], 1)
        self.issues = []

        applied = MigrationRecorder.Migration.objects.filter(
            app="service_requests", name=MIGRATION_NAME,
        ).exists()
        self.stdout.write(
            f"service_requests.{MIGRATION_NAME}: {'APPLIED' if applied else 'NOT APPLIED'}"
        )
        if applied:
            self._add(
                "WARNING", "migration_already_applied", [],
                "Preflight is reporting current state; it cannot retroactively gate an applied migration.",
            )

        self._check_service_requests()
        self._check_relationships_and_offerings()
        self._check_legacy_definitions()
        self._check_versioned_definitions()

        blockers = [issue for issue in self.issues if issue["status"] == "BLOCKING"]
        warnings = [issue for issue in self.issues if issue["status"] == "WARNING"]
        self.stdout.write("")
        if blockers:
            result = "BLOCKED"
        elif warnings:
            result = "WARNINGS_ONLY"
        else:
            result = "SAFE"
        self.stdout.write(
            f"Result: {result} (blocking={len(blockers)}, warnings={len(warnings)})"
        )
        if blockers:
            raise CommandError("Operation catalog preflight found blocking risks.")

    def _add(self, status, category, ids, detail):
        ids = sorted({int(value) for value in ids if value is not None})
        self.issues.append({"status": status, "category": category, "ids": ids, "detail": detail})
        shown_ids = ids[:self.max_ids]
        suffix = f" ids={shown_ids}" if shown_ids else ""
        if len(ids) > self.max_ids:
            suffix += f" (+{len(ids) - self.max_ids} more)"
        self.stdout.write(f"{status}: {category}: {detail}{suffix}")

    def _check_service_requests(self):
        missing_tenant = list(ServiceRequest.objects.filter(tenant_id__isnull=True).values_list("id", flat=True))
        missing_service = list(ServiceRequest.objects.filter(service_type_id__isnull=True).values_list("id", flat=True))
        if missing_tenant:
            self._add("BLOCKING", "service_request_missing_tenant", missing_tenant, "A ServiceRequest has no tenant reference.")
        if missing_service:
            self._add("BLOCKING", "service_request_missing_service_type", missing_service, "A ServiceRequest has no service type reference.")

        flagless = list(ServiceRequest.objects.filter(flag_id__isnull=True).values_list("id", flat=True))
        if flagless:
            self._add(
                "WARNING", "flagless_historical_service_requests", flagless,
                "Flagless rows are not inferred; each row needs an explicit migration decision.",
            )

        flagged_count = ServiceRequest.objects.filter(flag_id__isnull=False).count()
        if flagged_count > self.large_data_threshold:
            flagged_ids = ServiceRequest.objects.filter(flag_id__isnull=False).values_list("id", flat=True)[:self.max_ids]
            self._add(
                "WARNING", "large_flagged_service_request_population", flagged_ids,
                f"{flagged_count} flagged rows will create catalog history and should be migrated in an operational window.",
            )

        offerings = {
            row["id"]: row for row in TenantServiceOffering.objects.values(
                "id", "tenant_id", "service_type_id", "flag_id", "flag_relationship_id",
            )
        }
        versions = {
            row["id"]: row for row in OperationTemplateVersion.objects.values(
                "id", "operation_template_id", "status",
            )
        }
        templates = {
            row["id"]: row for row in OperationTemplate.objects.values(
                "id", "service_offering_id",
            )
        }
        bad_offering_refs = []
        bad_version_refs = []
        for row in ServiceRequest.objects.values(
            "id", "tenant_id", "service_type_id", "flag_id",
            "service_offering_id", "operation_template_version_id",
        ):
            offering = offerings.get(row["service_offering_id"])
            if offering and (
                offering["tenant_id"] != row["tenant_id"]
                or offering["service_type_id"] != row["service_type_id"]
                or offering["flag_id"] != row["flag_id"]
            ):
                bad_offering_refs.append(row["id"])
            version = versions.get(row["operation_template_version_id"])
            template = templates.get(version["operation_template_id"]) if version else None
            version_offering = offerings.get(template["service_offering_id"]) if template else None
            if version_offering and (
                version_offering["tenant_id"] != row["tenant_id"]
                or version_offering["service_type_id"] != row["service_type_id"]
                or version_offering["flag_id"] != row["flag_id"]
            ):
                bad_version_refs.append(row["id"])
        if bad_offering_refs:
            self._add("BLOCKING", "service_request_cross_scope_offering_reference", bad_offering_refs, "ServiceRequest and offering tenant/service/flag values disagree.")
        if bad_version_refs:
            self._add("BLOCKING", "service_request_cross_scope_version_reference", bad_version_refs, "ServiceRequest and version offering tenant/service/flag values disagree.")

    def _check_relationships_and_offerings(self):
        relationships = {
            row["id"]: row for row in TenantFlagRelationship.objects.values(
                "id", "tenant_id", "flag_id", "registry_organization_id", "partner_organization_id",
            )
        }
        organization_ids = {
            row["id"]: row["tenant_id"]
            for row in Organization.objects.values("id", "tenant_id")
        }
        bad_relationships = []
        for row in relationships.values():
            organization_tenants = {
                organization_ids.get(row["registry_organization_id"]),
                organization_ids.get(row["partner_organization_id"]),
            } - {None}
            if any(tenant_id != row["tenant_id"] for tenant_id in organization_tenants):
                bad_relationships.append(row["id"])
        if bad_relationships:
            self._add("BLOCKING", "relationship_cross_tenant_organization", bad_relationships, "A flag relationship points at an organization owned by another tenant.")

        service_types = {
            row["id"]: row["flag_scope"]
            for row in ServiceType.objects.values("id", "flag_scope")
        }
        offerings = list(TenantServiceOffering.objects.values(
            "id", "tenant_id", "service_type_id", "flag_id", "flag_relationship_id",
            "status", "accepts_new_requests",
        ))
        invalid_offerings = []
        available_by_pair = defaultdict(list)
        for row in offerings:
            relationship = relationships.get(row["flag_relationship_id"])
            invalid = (
                row["flag_relationship_id"] is not None and (
                    relationship is None
                    or relationship["tenant_id"] != row["tenant_id"]
                    or relationship["flag_id"] != row["flag_id"]
                )
            )
            scope = service_types.get(row["service_type_id"])
            invalid = invalid or (
                scope == ServiceType.FlagScope.REQUIRED and row["flag_id"] is None
            ) or (
                scope == ServiceType.FlagScope.NOT_APPLICABLE and row["flag_id"] is not None
            )
            if invalid:
                invalid_offerings.append(row["id"])
            if row["status"] == TenantServiceOffering.Status.ACTIVE and row["accepts_new_requests"]:
                available_by_pair[(row["tenant_id"], row["service_type_id"], row["flag_id"])].append(row["id"])
        if invalid_offerings:
            self._add("BLOCKING", "invalid_tenant_service_offering_reference", invalid_offerings, "Offering tenant, flag relationship, or service flag scope is inconsistent.")

        for pair, offering_ids in available_by_pair.items():
            if len(offering_ids) > 1:
                self._add("BLOCKING", "ambiguous_active_offerings", offering_ids, "More than one active offering can accept the same tenant/service/flag request.")

        operation_templates = list(OperationTemplate.objects.values("id", "service_offering_id", "is_active", "is_default"))
        template_ids_by_offering = defaultdict(list)
        for template in operation_templates:
            if template["is_active"] and template["is_default"]:
                template_ids_by_offering[template["service_offering_id"]].append(template["id"])
        published_template_ids = set(
            OperationTemplateVersion.objects.filter(status=OperationTemplateVersion.Status.PUBLISHED)
            .values_list("operation_template_id", flat=True)
        )
        missing_defaults = [
            row["id"] for row in offerings
            if row["status"] == TenantServiceOffering.Status.ACTIVE
            and row["accepts_new_requests"]
            and not any(template_id in published_template_ids for template_id in template_ids_by_offering[row["id"]])
        ]
        if missing_defaults:
            self._add("BLOCKING", "active_offering_missing_default_published_version", missing_defaults, "An accepting offering has no active default template with a published version.")

    def _check_legacy_definitions(self):
        flagged_pairs = set(
            ServiceRequest.objects.filter(flag_id__isnull=False)
            .values_list("service_type_id", "flag_id")
        )
        for row in ServiceRequest.objects.filter(flag_id__isnull=False).values(
            "id", "service_type__code", "flag__code",
        ):
            projected_template_code = f"legacy-{row['service_type__code']}-{row['flag__code']}"
            if len(projected_template_code) > 80:
                self._add(
                    "WARNING", "legacy_operation_template_code_truncation", [row["id"]],
                    "The migration will truncate the projected legacy operation template code.",
                )
        checklists = list(ChecklistTemplate.objects.filter(
            operation_template_version__isnull=True, is_active=True,
        ).values("id", "service_type_id", "flag_id", "document_type_id", "code"))
        checklist_groups = defaultdict(list)
        for row in checklists:
            checklist_groups[(row["service_type_id"], row["flag_id"])].append(row)
        for key, rows in checklist_groups.items():
            codes = defaultdict(list)
            for row in rows:
                raw_code = row["code"] or f"document-{row['document_type_id']}"
                code = raw_code[:80]
                codes[code].append(row["id"])
                if len(raw_code) > 80:
                    self._add("WARNING", "legacy_checklist_code_truncation", [row["id"]], "A projected checklist stable code exceeds the versioned limit.")
            for code, ids in codes.items():
                if len(ids) > 1 and key in flagged_pairs:
                    self._add("BLOCKING", "duplicate_legacy_checklist_stable_code", ids, f"Projected checklist code '{code}' would collide in one version.")

        steps = list(WorkflowStepTemplate.objects.filter(
            operation_template_version__isnull=True,
        ).prefetch_related("depends_on"))
        by_scope = defaultdict(list)
        for step in steps:
            by_scope[(step.service_type_id, step.flag_id)].append(step)
        for service_type_id, flag_id in flagged_pairs:
            specific = by_scope[(service_type_id, flag_id)]
            flagless = by_scope[(service_type_id, None)]
            selected = []
            selected_by_code = {}
            for step in specific + flagless:
                if step.code in selected_by_code:
                    existing = selected_by_code[step.code]
                    if step.flag_id == flag_id or (
                        step.flag_id is None and existing.flag_id is None
                    ):
                        self._add("BLOCKING", "duplicate_legacy_workflow_stable_code", [existing.id, step.id], f"Workflow code '{step.code}' is duplicated in one migrated scope.")
                    else:
                        self._add("WARNING", "specific_and_flagless_workflow_code_overlap", [selected_by_code[step.code].id, step.id], f"Workflow code '{step.code}' uses flag-specific precedence during backfill.")
                    continue
                selected_by_code[step.code] = step
                selected.append(step)

            graph = {step.code: set() for step in selected}
            for step in selected:
                for dependency in step.depends_on.all():
                    if dependency.code not in selected_by_code:
                        self._add("BLOCKING", "legacy_workflow_missing_dependency", [step.id, dependency.id], f"Workflow step '{step.code}' depends on a code that will not be copied.")
                        continue
                    if dependency.service_type_id != service_type_id or dependency.flag_id not in {None, flag_id}:
                        self._add("BLOCKING", "legacy_workflow_cross_scope_dependency", [step.id, dependency.id], "A dependency points outside the migrated service/flag scope.")
                    graph[step.code].add(dependency.code)
            if self._has_cycle(graph):
                self._add("BLOCKING", "legacy_workflow_dependency_cycle", [step.id for step in selected], "The selected legacy workflow graph contains a cycle.")

    def _check_versioned_definitions(self):
        for version in OperationTemplateVersion.objects.all().prefetch_related(
            "workflow_step_templates__depends_on", "checklist_templates",
        ):
            steps = list(version.workflow_step_templates.all())
            step_ids_by_code = defaultdict(list)
            for step in steps:
                step_ids_by_code[step.code].append(step.id)
            duplicate_step_ids = [step_id for ids in step_ids_by_code.values() if len(ids) > 1 for step_id in ids]
            if duplicate_step_ids:
                self._add("BLOCKING", "duplicate_versioned_workflow_stable_code", duplicate_step_ids, "Workflow step codes must be unique inside a version.")
            graph = {step.id: set() for step in steps}
            for step in steps:
                for dependency in step.depends_on.all():
                    if dependency.operation_template_version_id != version.id:
                        self._add("BLOCKING", "versioned_cross_version_dependency", [step.id, dependency.id], "A versioned workflow dependency points outside its version.")
                    else:
                        graph[step.id].add(dependency.id)
            if self._has_cycle(graph):
                self._add("BLOCKING", "versioned_workflow_dependency_cycle", [step.id for step in steps], "A versioned workflow graph contains a cycle.")
            checklist_codes = defaultdict(list)
            for checklist in version.checklist_templates.filter(is_active=True):
                checklist_codes[checklist.code].append(checklist.id)
            duplicate_checklist_ids = [checklist_id for ids in checklist_codes.values() if len(ids) > 1 for checklist_id in ids]
            if duplicate_checklist_ids:
                self._add("BLOCKING", "duplicate_versioned_checklist_stable_code", duplicate_checklist_ids, "Checklist codes must be unique inside a version.")

    @staticmethod
    def _has_cycle(graph):
        visiting = set()
        visited = set()

        def visit(node):
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(dependency) for dependency in graph.get(node, ())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph)
