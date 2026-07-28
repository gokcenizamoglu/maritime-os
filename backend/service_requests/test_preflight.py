from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase

from catalog.models import DocumentType, Flag, ServiceType, TenantServiceOffering
from checklists.models import ChecklistTemplate
from customers.models import Customer
from organizations.models import TenantFlagRelationship
from service_requests.models import ServiceRequest
from tenants.models import Tenant
from users.models import User
from vessels.models import Vessel
from workflow.models import WorkflowStepTemplate


class OperationCatalogPreflightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Preflight Tenant", slug="preflight-tenant")
        cls.user = User.objects.create_user(username="preflight-user", password="pass", tenant=cls.tenant)
        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Preflight Customer")
        cls.vessel = Vessel.objects.create(
            tenant=cls.tenant, customer=cls.customer, name="MV Preflight", imo_number="IMO-PREFLIGHT",
        )

    def _request(self, service_type, flag=None, reference="PREFLIGHT-1"):
        return ServiceRequest.objects.create(
            tenant=self.tenant, customer=self.customer, vessel=self.vessel,
            service_type=service_type, flag=flag, created_by=self.user,
            reference_code=reference,
        )

    def test_flagless_rows_are_reported_without_inference_or_writes(self):
        service_type = ServiceType.objects.create(
            name="Flagless Preflight Service", code="flagless_preflight", flag_scope=ServiceType.FlagScope.OPTIONAL,
        )
        request = self._request(service_type, reference="PREFLIGHT-FLAGLESS")
        before = {
            "requests": ServiceRequest.objects.count(),
            "offerings": TenantServiceOffering.objects.count(),
            "relationships": TenantFlagRelationship.objects.count(),
        }
        output = StringIO()
        call_command("preflight_operation_catalog", stdout=output)
        self.assertIn("flagless_historical_service_requests", output.getvalue())
        self.assertIn(str(request.id), output.getvalue())
        self.assertIn("not inferred", output.getvalue())
        self.assertEqual(ServiceRequest.objects.count(), before["requests"])
        self.assertEqual(TenantServiceOffering.objects.count(), before["offerings"])
        self.assertEqual(TenantFlagRelationship.objects.count(), before["relationships"])

    def test_duplicate_legacy_checklist_code_is_blocking(self):
        service_type = ServiceType.objects.create(
            name="Checklist Preflight Service", code="checklist_preflight", flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        flag = Flag.objects.create(name="Preflight Flag", code="PFL")
        first_document = DocumentType.objects.create(name="Preflight Doc A", code="preflight-doc-a")
        second_document = DocumentType.objects.create(name="Preflight Doc B", code="preflight-doc-b")
        ChecklistTemplate.objects.create(
            service_type=service_type, flag=flag, document_type=first_document, code="same-stable-code",
        )
        ChecklistTemplate.objects.create(
            service_type=service_type, flag=flag, document_type=second_document, code="same-stable-code",
        )
        self._request(service_type, flag, reference="PREFLIGHT-DUPLICATE")

        with self.assertRaises(CommandError):
            call_command("preflight_operation_catalog", stdout=StringIO())

    def test_legacy_workflow_cycle_is_blocking(self):
        service_type = ServiceType.objects.create(
            name="Cycle Preflight Service", code="cycle_preflight", flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        flag = Flag.objects.create(name="Cycle Flag", code="CYC")
        first = WorkflowStepTemplate.objects.create(service_type=service_type, flag=flag, code="first", name="First")
        second = WorkflowStepTemplate.objects.create(service_type=service_type, flag=flag, code="second", name="Second")
        first.depends_on.add(second)
        second.depends_on.add(first)
        self._request(service_type, flag, reference="PREFLIGHT-CYCLE")

        with self.assertRaises(CommandError):
            call_command("preflight_operation_catalog", stdout=StringIO())
