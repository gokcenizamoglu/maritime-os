from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authorization.models import TenantRole
from authorization.services import assign_role, provision_default_roles
from catalog.models import DocumentType, Flag, ServiceType, TenantServiceOffering
from checklists.models import ChecklistTemplate
from organizations.models import TenantFlagRelationship
from service_requests.services import (
    CrossTenantReferenceError,
    InvalidServiceRequestConfiguration,
    create_service_request,
)
from users.models import User
from workflow.models import (
    OperationTemplate, OperationTemplateVersion, WorkflowStepDependency,
    WorkflowStepInstance, WorkflowStepTemplate,
)
from workflow.services import (
    clone_published_version,
    create_draft_version,
    archive_version,
    publish_version,
    retire_version,
    update_step_status,
)


class TenantCatalogAndOperationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = cls._tenant("Tenant A", "tenant-a-catalog")
        cls.other_tenant = cls._tenant("Tenant B", "tenant-b-catalog")
        cls.user = User.objects.create_user(username="catalog-user", password="pass", tenant=cls.tenant)
        provision_default_roles(cls.tenant)
        assign_role(user=cls.user, role=TenantRole.objects.get(tenant=cls.tenant, name="Tenant Admin"))
        cls.customer = cls._customer(cls.tenant, "Customer A")
        cls.vessel = cls._vessel(cls.tenant, cls.customer, "MV A", "IMO-A")
        cls.other_customer = cls._customer(cls.other_tenant, "Customer B")
        cls.other_vessel = cls._vessel(cls.other_tenant, cls.other_customer, "MV B", "IMO-B")
        cls.service_type = ServiceType.objects.create(
            name="Owner Change", code="owner_change", flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        cls.flag = Flag.objects.create(name="Panama", code="PA")
        cls.document_type = DocumentType.objects.create(name="Passport", code="passport")
        cls.relationship = TenantFlagRelationship.objects.create(
            tenant=cls.tenant, flag=cls.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.DIRECT,
            status=TenantFlagRelationship.Status.ACTIVE,
        )
        cls.offering = TenantServiceOffering.objects.create(
            tenant=cls.tenant, service_type=cls.service_type, flag=cls.flag,
            flag_relationship=cls.relationship, display_name="Panama Owner Change",
            status=TenantServiceOffering.Status.ACTIVE, accepts_new_requests=True,
        )
        cls.template = OperationTemplate.objects.create(
            service_offering=cls.offering, name="Standard", code="standard", is_default=True,
        )
        cls.version = create_draft_version(tenant=cls.tenant, operation_template=cls.template)
        cls.checklist = ChecklistTemplate.objects.create(
            operation_template_version=cls.version, code="passport", document_type=cls.document_type,
        )
        cls.step = WorkflowStepTemplate.objects.create(
            operation_template_version=cls.version, code="document_review", name="Document review",
        )
        cls.version = publish_version(tenant=cls.tenant, version=cls.version, published_by=cls.user)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def _tenant(name, slug):
        from tenants.models import Tenant
        return Tenant.objects.create(name=name, slug=slug)

    @staticmethod
    def _customer(tenant, name):
        from customers.models import Customer
        return Customer.objects.create(tenant=tenant, name=name)

    @staticmethod
    def _vessel(tenant, customer, name, imo):
        from vessels.models import Vessel
        return Vessel.objects.create(tenant=tenant, customer=customer, name=name, imo_number=imo)

    def test_service_request_is_bound_to_offering_and_published_version(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )

        self.assertEqual(service_request.service_offering_id, self.offering.id)
        self.assertEqual(service_request.operation_template_version_id, self.version.id)
        self.assertEqual(service_request.service_type_id, self.service_type.id)
        self.assertEqual(service_request.flag_id, self.flag.id)
        self.assertEqual(service_request.checklist_items.get().source_template_id, self.checklist.id)
        self.assertEqual(
            service_request.workflow_steps.get().step_template.operation_template_version_id,
            self.version.id,
        )

    def test_legacy_pair_requires_one_active_offering_and_never_global_falls_back(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_type=self.service_type, flag=self.flag, created_by=self.user,
        )
        self.assertEqual(service_request.service_offering_id, self.offering.id)

        self.offering.accepts_new_requests = False
        self.offering.save(update_fields=["accepts_new_requests", "updated_at"])
        with self.assertRaises(InvalidServiceRequestConfiguration):
            create_service_request(
                tenant=self.tenant, customer=self.customer, vessel=self.vessel,
                service_type=self.service_type, flag=self.flag, created_by=self.user,
            )

    def test_cross_tenant_offering_is_rejected(self):
        with self.assertRaises(CrossTenantReferenceError):
            create_service_request(
                tenant=self.other_tenant, customer=self.other_customer, vessel=self.other_vessel,
                service_offering=self.offering, created_by=self.user,
            )

    def test_expired_relationship_cannot_open_new_request(self):
        self.relationship.valid_until = timezone.localdate() - timedelta(days=1)
        self.relationship.save(update_fields=["valid_until", "updated_at"])
        with self.assertRaises(InvalidServiceRequestConfiguration):
            create_service_request(
                tenant=self.tenant, customer=self.customer, vessel=self.vessel,
                service_offering=self.offering, created_by=self.user,
            )

    def test_flag_independent_service_can_open_without_flag(self):
        service_type = ServiceType.objects.create(
            name="Corporate Advisory", code="corporate_advisory",
            flag_scope=ServiceType.FlagScope.NOT_APPLICABLE,
        )
        offering = TenantServiceOffering.objects.create(
            tenant=self.tenant, service_type=service_type,
            display_name="Corporate Advisory", status=TenantServiceOffering.Status.ACTIVE,
            accepts_new_requests=True,
        )
        template = OperationTemplate.objects.create(
            service_offering=offering, name="Standard", code="standard", is_default=True,
        )
        version = create_draft_version(tenant=self.tenant, operation_template=template)
        publish_version(tenant=self.tenant, version=version, published_by=self.user)

        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=offering, created_by=self.user,
        )
        self.assertIsNone(service_request.flag_id)

    def test_relationship_deactivation_does_not_break_existing_operation(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        self.relationship.status = TenantFlagRelationship.Status.INACTIVE
        self.relationship.save(update_fields=["status", "updated_at"])

        step = service_request.workflow_steps.get()
        update_step_status(
            step_instance=step, status=WorkflowStepInstance.Status.ACTIVE, actor_user=self.user,
        )
        self.assertEqual(step.status, WorkflowStepInstance.Status.ACTIVE)

    def test_published_version_is_immutable_and_new_version_is_used_only_for_new_cases(self):
        old_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                self.checklist.code = "changed"
                self.checklist.save()
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                self.step.name = "changed"
                self.step.save()
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                self.step.depends_on.clear()

        draft = clone_published_version(
            tenant=self.tenant, source_version=self.version, created_by=self.user,
        )
        draft_checklist = draft.checklist_templates.get()
        draft_checklist.min_count = 2
        ChecklistTemplate.objects.bulk_update([draft_checklist], ["min_count"])
        draft_checklist.refresh_from_db()
        self.assertEqual(draft_checklist.min_count, 2)
        second_step = WorkflowStepTemplate.objects.create(
            operation_template_version=draft, code="registry_submission", name="Registry submission",
        )
        publish_version(tenant=self.tenant, version=draft, published_by=self.user)

        new_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        self.assertEqual(old_request.operation_template_version_id, self.version.id)
        self.assertEqual(new_request.operation_template_version_id, draft.id)
        self.assertTrue(old_request.workflow_steps.filter(step_template__code="document_review").exists())
        self.assertFalse(old_request.workflow_steps.filter(step_template__code=second_step.code).exists())
        self.assertTrue(new_request.workflow_steps.filter(step_template__code=second_step.code).exists())

    def test_service_without_published_default_version_is_rejected(self):
        self.template.is_default = False
        self.template.save(update_fields=["is_default", "updated_at"])
        with self.assertRaises(InvalidServiceRequestConfiguration):
            create_service_request(
                tenant=self.tenant, customer=self.customer, vessel=self.vessel,
                service_offering=self.offering, created_by=self.user,
            )

    def test_offering_api_is_tenant_scoped(self):
        other_relationship = TenantFlagRelationship.objects.create(
            tenant=self.other_tenant, flag=self.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.DIRECT,
            status=TenantFlagRelationship.Status.ACTIVE,
        )
        other_offering = TenantServiceOffering.objects.create(
            tenant=self.other_tenant, service_type=self.service_type, flag=self.flag,
            flag_relationship=other_relationship, status=TenantServiceOffering.Status.ACTIVE,
            accepts_new_requests=True,
        )
        response = self.client.get("/api/service-offerings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [self.offering.id])
        self.assertEqual(self.client.get(f"/api/service-offerings/{other_offering.id}/").status_code, 404)

    def test_published_retired_and_archived_orm_write_paths_are_blocked(self):
        with self.assertRaises(ValidationError):
            OperationTemplateVersion.objects.filter(pk=self.version.pk).update(published_at=None)

        version_copy = OperationTemplateVersion.objects.get(pk=self.version.pk)
        version_copy.version_number = 99
        with self.assertRaises(ValidationError):
            OperationTemplateVersion.objects.filter(pk=self.version.pk).bulk_update(
                [version_copy], ["version_number"],
            )
        with self.assertRaises(ValidationError):
            OperationTemplateVersion.objects.filter(pk=self.version.pk).delete()
        with self.assertRaises(ValidationError):
            OperationTemplateVersion.objects.bulk_create([
                OperationTemplateVersion(
                    operation_template=self.template,
                    version_number=99,
                    status=OperationTemplateVersion.Status.PUBLISHED,
                ),
            ])

        with self.assertRaises(ValidationError):
            ChecklistTemplate.objects.filter(pk=self.checklist.pk).update(code="blocked")
        with self.assertRaises(ValidationError):
            ChecklistTemplate.objects.bulk_create([
                ChecklistTemplate(
                    operation_template_version=self.version,
                    code="blocked-2",
                    document_type=self.document_type,
                ),
            ])
        with self.assertRaises(ValidationError):
            WorkflowStepTemplate.objects.filter(pk=self.step.pk).delete()
        with self.assertRaises(ValidationError):
            WorkflowStepDependency.objects.bulk_create([
                WorkflowStepDependency(
                    from_workflowsteptemplate=self.step,
                    to_workflowsteptemplate=self.step,
                ),
            ])

        retired = retire_version(tenant=self.tenant, version=self.version)
        retired.version_number = 100
        with self.assertRaises(ValidationError):
            retired.save()
        archived = archive_version(tenant=self.tenant, version=retired)
        self.assertEqual(archived.status, OperationTemplateVersion.Status.ARCHIVED)
        with self.assertRaises(ValidationError):
            OperationTemplateVersion.objects.filter(pk=archived.pk).delete()
