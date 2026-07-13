"""
Tests for the pagination/filter/search/ordering added to
ServiceRequestViewSet this sprint (see that class's module docstring).

Deliberately does NOT re-test: the list/detail serializer field shapes
(unchanged this sprint — a separate follow-up), the create/transition
flows (state_machine's own concern), or reference_code generation
(service_requests/models.py::ServiceRequestSequence's own concern).
"""
from catalog.models import Flag, ServiceType
from customers.models import Customer
from rest_framework import status
from rest_framework.test import APITestCase
from service_requests.models import ServiceRequest
from tenants.models import Tenant
from users.models import User
from vessels.models import Vessel

LIST_URL = "/api/service-requests/"


class ServiceRequestQueryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine")
        cls.other_tenant = Tenant.objects.create(name="Other Co", slug="other-co")
        cls.user = User.objects.create(username="ops-user", tenant=cls.tenant)

        cls.customer_a = Customer.objects.create(tenant=cls.tenant, name="Acme Shipping")
        cls.customer_b = Customer.objects.create(tenant=cls.tenant, name="Beta Maritime")
        cls.vessel_a = Vessel.objects.create(
            tenant=cls.tenant, customer=cls.customer_a, name="MV Alpha", imo_number="1111111",
        )
        cls.vessel_b = Vessel.objects.create(
            tenant=cls.tenant, customer=cls.customer_b, name="MV Beta", imo_number="2222222",
        )
        cls.service_type_owner_change = ServiceType.objects.create(name="Owner Change", code="owner_change")
        cls.service_type_crew = ServiceType.objects.create(name="Crew Endorsement", code="crew_endorsement")
        cls.flag_panama = Flag.objects.create(name="Panama", code="PA")
        cls.flag_palau = Flag.objects.create(name="Palau", code="PW")

        cls.sr_draft = ServiceRequest.objects.create(
            tenant=cls.tenant, customer=cls.customer_a, vessel=cls.vessel_a,
            service_type=cls.service_type_owner_change, flag=cls.flag_panama,
            status=ServiceRequest.Status.DRAFT, reference_code="LM-2026-0001",
        )
        cls.sr_ready = ServiceRequest.objects.create(
            tenant=cls.tenant, customer=cls.customer_b, vessel=cls.vessel_b,
            service_type=cls.service_type_crew, flag=cls.flag_palau,
            status=ServiceRequest.Status.READY, reference_code="LM-2026-0002",
        )

        # Cross-tenant control row, deliberately sharing names with the
        # tenant-owned rows above — proves filters/search can't be tricked
        # into crossing tenant boundaries via a name/id collision.
        cls.other_customer = Customer.objects.create(tenant=cls.other_tenant, name="Acme Shipping")
        cls.other_vessel = Vessel.objects.create(
            tenant=cls.other_tenant, customer=cls.other_customer, name="MV Alpha", imo_number="9999999",
        )
        ServiceRequest.objects.create(
            tenant=cls.other_tenant, customer=cls.other_customer, vessel=cls.other_vessel,
            service_type=cls.service_type_owner_change, flag=cls.flag_panama,
            status=ServiceRequest.Status.DRAFT, reference_code="OC-2026-0001",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    # ---- pagination ----

    def test_list_response_has_the_paginated_envelope_shape(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), {"count", "next", "previous", "results"})

    def test_default_page_size_is_25(self):
        for i in range(30):
            ServiceRequest.objects.create(
                tenant=self.tenant, customer=self.customer_a, vessel=self.vessel_a,
                service_type=self.service_type_owner_change, flag=self.flag_panama,
                status=ServiceRequest.Status.DRAFT, reference_code=f"LM-2026-BULK-{i:03d}",
            )
        response = self.client.get(LIST_URL)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(response.data["count"], 32)  # 30 + 2 from setUpTestData, same tenant only
        self.assertIsNotNone(response.data["next"])

    def test_client_page_size_is_capped_at_max_page_size(self):
        for i in range(150):
            ServiceRequest.objects.create(
                tenant=self.tenant, customer=self.customer_a, vessel=self.vessel_a,
                service_type=self.service_type_owner_change, flag=self.flag_panama,
                status=ServiceRequest.Status.DRAFT, reference_code=f"LM-2026-CAP-{i:03d}",
            )
        response = self.client.get(LIST_URL, {"page_size": 1000})
        self.assertEqual(len(response.data["results"]), 100)  # StandardResultsPagination.max_page_size

    # ---- tenant isolation ----

    def test_list_never_includes_another_tenants_rows(self):
        response = self.client.get(LIST_URL)
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertNotIn("OC-2026-0001", codes)

    def test_filtering_cannot_reach_another_tenants_customer(self):
        response = self.client.get(LIST_URL, {"customer": self.other_customer.id})
        self.assertEqual(response.data["count"], 0)

    # ---- filtering ----

    def test_filter_by_status(self):
        response = self.client.get(LIST_URL, {"status": ServiceRequest.Status.READY})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_filter_by_customer(self):
        response = self.client.get(LIST_URL, {"customer": self.customer_a.id})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0001"})

    def test_filter_by_vessel(self):
        response = self.client.get(LIST_URL, {"vessel": self.vessel_b.id})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_filter_by_service_type(self):
        response = self.client.get(LIST_URL, {"service_type": self.service_type_crew.id})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_filter_by_flag(self):
        response = self.client.get(LIST_URL, {"flag": self.flag_palau.id})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    # ---- search ----

    def test_search_by_reference_code(self):
        response = self.client.get(LIST_URL, {"search": "LM-2026-0002"})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_search_by_customer_name(self):
        response = self.client.get(LIST_URL, {"search": "Beta Maritime"})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_search_by_vessel_name(self):
        # "MV Alpha" also exists on the OTHER tenant's vessel (deliberately,
        # see setUpTestData) — this proves search runs on top of the
        # tenant-scoped queryset, not instead of it.
        response = self.client.get(LIST_URL, {"search": "MV Alpha"})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0001"})

    def test_search_by_service_type_name(self):
        response = self.client.get(LIST_URL, {"search": "Crew Endorsement"})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    def test_search_by_flag_name(self):
        response = self.client.get(LIST_URL, {"search": "Palau"})
        codes = {row["reference_code"] for row in response.data["results"]}
        self.assertEqual(codes, {"LM-2026-0002"})

    # ---- ordering ----

    def test_ordering_by_created_at_ascending(self):
        response = self.client.get(LIST_URL, {"ordering": "created_at"})
        codes = [row["reference_code"] for row in response.data["results"]]
        self.assertEqual(codes, ["LM-2026-0001", "LM-2026-0002"])

    def test_ordering_by_updated_at_descending(self):
        response = self.client.get(LIST_URL, {"ordering": "-updated_at"})
        codes = [row["reference_code"] for row in response.data["results"]]
        self.assertEqual(codes[0], "LM-2026-0002")

    def test_ordering_by_reference_code(self):
        response = self.client.get(LIST_URL, {"ordering": "-reference_code"})
        codes = [row["reference_code"] for row in response.data["results"]]
        self.assertEqual(codes, ["LM-2026-0002", "LM-2026-0001"])

    def test_ordering_by_status(self):
        # "draft" < "ready" alphabetically — ascending order is the default
        # direction when the ?ordering= value has no "-" prefix.
        response = self.client.get(LIST_URL, {"ordering": "status"})
        codes = [row["reference_code"] for row in response.data["results"]]
        self.assertEqual(codes, ["LM-2026-0001", "LM-2026-0002"])

    def test_invalid_ordering_field_is_ignored_not_errored(self):
        # DRF's OrderingFilter silently drops any ?ordering= value not in
        # ordering_fields (falling back to ServiceRequest.Meta.ordering)
        # rather than erroring or allowing an arbitrary column — this
        # locks that safe default in as a regression check, since
        # ordering by an unapproved/nonexistent field (e.g. one that
        # doesn't exist on the model at all) must never 500 or leak
        # implementation details.
        response = self.client.get(LIST_URL, {"ordering": "password_hash"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [row["reference_code"] for row in response.data["results"]]
        self.assertEqual(codes, ["LM-2026-0002", "LM-2026-0001"])  # falls back to -created_at

    def test_invalid_status_filter_value_is_a_clean_400(self):
        # filterset_fields auto-generates a choice-validated filter for
        # `status` (it has model choices) — an unrecognized value must be
        # rejected with a normal validation error, not a crash.
        response = self.client.get(LIST_URL, {"status": "not_a_real_status"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_fk_filter_value_is_a_clean_400(self):
        response = self.client.get(LIST_URL, {"customer": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
