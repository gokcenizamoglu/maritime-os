from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from activity.models import ActivityLog
from authorization.models import TenantRole
from authorization.services import assign_role
from catalog.models import DocumentType, Flag, ServiceType, TenantServiceOffering
from checklists.models import ChecklistItem
from organizations.models import TenantFlagRelationship
from service_requests.models import ServiceRequest
from service_requests.services import create_service_request
from tenants.models import Tenant
from users.models import User
from vessels.models import Vessel
from customers.models import Customer
from workflow.models import OperationTemplate, WorkflowStepInstance
from workflow.services import create_draft_version, publish_version


class ServiceRequestMutationSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Safety Tenant", slug="safety-tenant")
        cls.other_tenant = Tenant.objects.create(name="Other Safety Tenant", slug="other-safety-tenant")
        cls.user = User.objects.create_user(username="safety-user", password="pass", tenant=cls.tenant)
        cls.other_user = User.objects.create_user(username="other-safety-user", password="pass", tenant=cls.other_tenant)
        assign_role(
            user=cls.user,
            role=TenantRole.objects.get(tenant=cls.tenant, name="Tenant Admin"),
        )
        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Safety Customer")
        cls.vessel = Vessel.objects.create(tenant=cls.tenant, customer=cls.customer, name="MV Safety", imo_number="IMO-SAFETY")
        cls.other_customer = Customer.objects.create(tenant=cls.other_tenant, name="Other Customer")
        cls.other_vessel = Vessel.objects.create(
            tenant=cls.other_tenant, customer=cls.other_customer, name="MV Other Safety", imo_number="IMO-OTHER-SAFETY",
        )
        cls.service_type = ServiceType.objects.create(
            name="Safety Owner Change", code="safety_owner_change", flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        cls.other_service_type = ServiceType.objects.create(
            name="Safety Registry Change", code="safety_registry_change", flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        cls.flag = Flag.objects.create(name="Safety Flag", code="SAF")
        cls.other_flag = Flag.objects.create(name="Other Safety Flag", code="OSF")
        cls.relationship = TenantFlagRelationship.objects.create(
            tenant=cls.tenant, flag=cls.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.DIRECT,
            status=TenantFlagRelationship.Status.ACTIVE,
        )
        cls.same_tenant_relationship = TenantFlagRelationship.objects.create(
            tenant=cls.tenant, flag=cls.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.CORRESPONDENT,
            status=TenantFlagRelationship.Status.INACTIVE,
        )
        cls.offering = cls._offering(cls.tenant, cls.service_type, cls.flag, cls.relationship, "Safety offering", True)
        cls.same_tenant_offering = cls._offering(
            cls.tenant, cls.service_type, cls.flag, cls.same_tenant_relationship, "Other safety offering", False,
        )
        cls.other_relationship = TenantFlagRelationship.objects.create(
            tenant=cls.other_tenant, flag=cls.other_flag,
            relationship_type=TenantFlagRelationship.RelationshipType.DIRECT,
            status=TenantFlagRelationship.Status.INACTIVE,
        )
        cls.foreign_offering = cls._offering(
            cls.other_tenant, cls.other_service_type, cls.other_flag, cls.other_relationship, "Foreign offering", False,
        )

    @staticmethod
    def _offering(tenant, service_type, flag, relationship, name, accepts):
        offering = TenantServiceOffering.objects.create(
            tenant=tenant, service_type=service_type, flag=flag,
            flag_relationship=relationship, display_name=name,
            status=TenantServiceOffering.Status.ACTIVE if accepts else TenantServiceOffering.Status.INACTIVE,
            accepts_new_requests=accepts,
        )
        template = OperationTemplate.objects.create(
            service_offering=offering, name="Safety template", code=f"template-{offering.id}", is_default=True,
        )
        version = create_draft_version(tenant=tenant, operation_template=template)
        publish_version(tenant=tenant, version=version)
        return offering

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_put_and_patch_cannot_change_immutable_relations_or_status(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        snapshot = {
            "customer": service_request.customer_id,
            "vessel": service_request.vessel_id,
            "service_type": service_request.service_type_id,
            "flag": service_request.flag_id,
            "service_offering": service_request.service_offering_id,
            "operation_template_version": service_request.operation_template_version_id,
            "status": service_request.status,
            "checklists": list(service_request.checklist_items.values_list("id", flat=True)),
            "workflow": list(service_request.workflow_steps.values_list("id", flat=True)),
        }
        url = f"/api/service-requests/{service_request.id}/"
        payload = {
            "customer": self.other_customer.id,
            "vessel": self.other_vessel.id,
            "service_type": self.other_service_type.id,
            "flag": self.other_flag.id,
            "service_offering": self.same_tenant_offering.id,
            "operation_template_version": OperationTemplate.objects.get(
                service_offering=self.same_tenant_offering,
            ).versions.get().id,
            "status": ServiceRequest.Status.COMPLETED,
        }
        self.assertEqual(self.client.patch(url, payload, format="json").status_code, 405)
        self.assertEqual(self.client.put(url, payload, format="json").status_code, 405)

        service_request.refresh_from_db()
        self.assertEqual(service_request.customer_id, snapshot["customer"])
        self.assertEqual(service_request.vessel_id, snapshot["vessel"])
        self.assertEqual(service_request.service_type_id, snapshot["service_type"])
        self.assertEqual(service_request.flag_id, snapshot["flag"])
        self.assertEqual(service_request.service_offering_id, snapshot["service_offering"])
        self.assertEqual(service_request.operation_template_version_id, snapshot["operation_template_version"])
        self.assertEqual(service_request.status, snapshot["status"])
        self.assertEqual(list(service_request.checklist_items.values_list("id", flat=True)), snapshot["checklists"])
        self.assertEqual(list(service_request.workflow_steps.values_list("id", flat=True)), snapshot["workflow"])

    def test_foreign_offering_and_version_ids_are_not_an_update_path(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        foreign_version = OperationTemplate.objects.get(
            service_offering=self.foreign_offering,
        ).versions.get()
        response = self.client.patch(
            f"/api/service-requests/{service_request.id}/",
            {"service_offering": self.foreign_offering.id, "operation_template_version": foreign_version.id},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
        service_request.refresh_from_db()
        self.assertEqual(service_request.service_offering_id, self.offering.id)
        self.assertEqual(service_request.operation_template_version_id, self.offering.operation_templates.get().versions.get().id)

    def test_transition_service_changes_status_and_writes_activity(self):
        service_request = create_service_request(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_offering=self.offering, created_by=self.user,
        )
        response = self.client.post(
            f"/api/service-requests/{service_request.id}/transition/",
            {"target_status": ServiceRequest.Status.COLLECTING_DOCUMENTS},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        service_request.refresh_from_db()
        self.assertEqual(service_request.status, ServiceRequest.Status.COLLECTING_DOCUMENTS)
        self.assertTrue(ActivityLog.objects.filter(
            service_request=service_request,
            verb="service_request.status_changed",
        ).exists())

    def test_instance_generation_failure_rolls_back_service_request(self):
        before_requests = ServiceRequest.objects.count()
        before_checklists = ChecklistItem.objects.count()
        before_workflow_steps = WorkflowStepInstance.objects.count()
        with patch(
            "service_requests.services.generate_workflow_steps_for_service_request",
            side_effect=RuntimeError("workflow generation failed"),
        ):
            with self.assertRaises(RuntimeError):
                create_service_request(
                    tenant=self.tenant, customer=self.customer, vessel=self.vessel,
                    service_offering=self.offering, created_by=self.user,
                )
        self.assertEqual(ServiceRequest.objects.count(), before_requests)
        self.assertEqual(ChecklistItem.objects.count(), before_checklists)
        self.assertEqual(WorkflowStepInstance.objects.count(), before_workflow_steps)
