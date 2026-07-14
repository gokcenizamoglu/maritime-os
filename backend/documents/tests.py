"""
Tests for the `service_request` query-param filter added to
DocumentViewSet this sprint (see that class's get_queryset()). Does not
touch upload/classify behavior — those are unmodified.
"""
from authorization.test_helpers import grant_all_capabilities
from catalog.models import Flag, ServiceType
from customers.models import Customer
from django.core.files.uploadedfile import SimpleUploadedFile
from documents.models import Document
from rest_framework import status
from rest_framework.test import APITestCase
from service_requests.models import ServiceRequest
from tenants.models import Tenant
from users.models import User
from vessels.models import Vessel

LIST_URL = "/api/documents/"


class DocumentServiceRequestFilterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine-docs")
        cls.other_tenant = Tenant.objects.create(name="Other Co", slug="other-co-docs")
        cls.user = User.objects.create(username="ops-user", tenant=cls.tenant)
        grant_all_capabilities(cls.user)

        customer = Customer.objects.create(tenant=cls.tenant, name="Acme Shipping")
        vessel = Vessel.objects.create(tenant=cls.tenant, customer=customer, name="MV Test", imo_number="1234567")
        service_type = ServiceType.objects.create(name="Owner Change", code="owner_change")
        flag = Flag.objects.create(name="Panama", code="PA")

        cls.service_request = ServiceRequest.objects.create(
            tenant=cls.tenant, customer=customer, vessel=vessel,
            service_type=service_type, flag=flag,
            status=ServiceRequest.Status.DRAFT, reference_code="LM-2026-0001",
        )
        cls.other_service_request = ServiceRequest.objects.create(
            tenant=cls.tenant, customer=customer, vessel=vessel,
            service_type=service_type, flag=flag,
            status=ServiceRequest.Status.DRAFT, reference_code="LM-2026-0002",
        )

        cls.document_on_target = Document.objects.create(
            tenant=cls.tenant, service_request=cls.service_request,
            file=SimpleUploadedFile("a.pdf", b"content"), original_filename="a.pdf",
            uploaded_by_type=Document.UploadedByType.INTERNAL,
        )
        cls.document_on_other = Document.objects.create(
            tenant=cls.tenant, service_request=cls.other_service_request,
            file=SimpleUploadedFile("b.pdf", b"content"), original_filename="b.pdf",
            uploaded_by_type=Document.UploadedByType.INTERNAL,
        )

        # Cross-tenant service request + document — must be unreachable
        # regardless of a correct, existing id.
        other_customer = Customer.objects.create(tenant=cls.other_tenant, name="Other Customer")
        other_vessel = Vessel.objects.create(
            tenant=cls.other_tenant, customer=other_customer, name="MV Other", imo_number="7654321",
        )
        cls.foreign_service_request = ServiceRequest.objects.create(
            tenant=cls.other_tenant, customer=other_customer, vessel=other_vessel,
            service_type=service_type, flag=flag,
            status=ServiceRequest.Status.DRAFT, reference_code="OC-2026-0001",
        )
        Document.objects.create(
            tenant=cls.other_tenant, service_request=cls.foreign_service_request,
            file=SimpleUploadedFile("c.pdf", b"content"), original_filename="c.pdf",
            uploaded_by_type=Document.UploadedByType.INTERNAL,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_filter_by_service_request_returns_only_that_cases_documents(self):
        response = self.client.get(LIST_URL, {"service_request": self.service_request.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.document_on_target.id})

    def test_filter_excludes_other_service_requests_documents_in_same_tenant(self):
        response = self.client.get(LIST_URL, {"service_request": self.service_request.id})
        ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.document_on_other.id, ids)

    def test_cross_tenant_service_request_id_is_not_found(self):
        # Existing, valid id — just not this tenant's. Must 404, not
        # silently return an empty list (which would look identical to
        # "this case genuinely has no documents").
        response = self.client.get(LIST_URL, {"service_request": self.foreign_service_request.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_service_request_id_is_not_found(self):
        response = self.client.get(LIST_URL, {"service_request": 999999})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_non_numeric_service_request_id_is_not_found(self):
        response = self.client.get(LIST_URL, {"service_request": "abc"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_without_filter_is_paginated(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), {"count", "next", "previous", "results"})
