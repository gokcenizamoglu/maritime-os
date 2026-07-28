from authorization.test_helpers import grant_all_capabilities
from authorization.models import TenantRole, UserRoleAssignment
from authorization.services import provision_default_roles, sync_capabilities
from django.db import IntegrityError
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase
from customers.models import Customer
from tenants.models import Tenant
from users.models import User
from vessels.models import Vessel

LIST_URL = "/api/vessels/"


def detail_url(pk):
    return f"/api/vessels/{pk}/"


class VesselCRUDTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine")
        cls.other_tenant = Tenant.objects.create(name="Other Co", slug="other-co")
        cls.user = User.objects.create(username="ops-user", tenant=cls.tenant)
        grant_all_capabilities(cls.user)

        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Acme Shipping")
        cls.other_customer = Customer.objects.create(tenant=cls.other_tenant, name="Other Shipping")

        cls.vessel = Vessel.objects.create(
            tenant=cls.tenant, customer=cls.customer,
            name="MV Alpha", imo_number="1234567",
        )
        cls.other_vessel = Vessel.objects.create(
            tenant=cls.other_tenant, customer=cls.other_customer,
            name="MV Beta", imo_number="7654321",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_own_tenant(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in response.data["results"]]
        self.assertIn(self.vessel.id, ids)
        self.assertNotIn(self.other_vessel.id, ids)

    def test_list_has_paginated_envelope(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(set(response.data.keys()), {"count", "next", "previous", "results"})

    def test_list_includes_related_names(self):
        response = self.client.get(LIST_URL)
        vessel_data = response.data["results"][0]
        self.assertIn("customer_name", vessel_data)

    def test_filter_by_customer(self):
        other_customer = Customer.objects.create(tenant=self.tenant, name="Beta Co")
        Vessel.objects.create(
            tenant=self.tenant, customer=other_customer,
            name="MV Gamma", imo_number="9999999",
        )
        response = self.client.get(LIST_URL, {"customer": self.customer.id})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "MV Alpha")

    def test_retrieve_own_tenant(self):
        response = self.client.get(detail_url(self.vessel.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "MV Alpha")

    def test_retrieve_cross_tenant_returns_404(self):
        response = self.client.get(detail_url(self.other_vessel.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_vessel(self):
        data = {
            "customer": self.customer.id,
            "name": "MV New",
            "imo_number": "5555555",
        }
        response = self.client.post(LIST_URL, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "MV New")
        created = Vessel.objects.get(id=response.data["id"])
        self.assertEqual(created.tenant_id, self.tenant.id)

    def test_client_cannot_choose_vessel_tenant(self):
        response = self.client.post(
            LIST_URL,
            {
                "customer": self.customer.id,
                "tenant": self.other_tenant.id,
                "name": "Server Tenant Wins",
                "imo_number": "TENANT-CHOICE",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Vessel.objects.get(id=response.data["id"])
        self.assertEqual(created.tenant_id, self.tenant.id)
        self.assertNotIn("tenant", response.data)

    def test_create_rejects_cross_tenant_customer(self):
        data = {
            "customer": self.other_customer.id,
            "name": "MV Sneaky",
            "imo_number": "8888888",
        }
        response = self.client.post(LIST_URL, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_enforces_unique_imo_per_tenant(self):
        data = {
            "customer": self.customer.id,
            "name": "MV Duplicate",
            "imo_number": "1234567",
        }
        response = self.client.post(LIST_URL, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update(self):
        response = self.client.patch(
            detail_url(self.vessel.id),
            {"vessel_type": "Bulk Carrier"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vessel.refresh_from_db()
        self.assertEqual(self.vessel.vessel_type, "Bulk Carrier")

    def test_cross_tenant_update_returns_404(self):
        response = self.client.patch(
            detail_url(self.other_vessel.id),
            {"name": "Hacked"},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_not_allowed(self):
        response = self.client.delete(detail_url(self.vessel.id))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_not_allowed(self):
        response = self.client.put(
            detail_url(self.vessel.id),
            {"name": "Full Update", "customer": self.customer.id, "imo_number": "1234567"},
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_by_imo(self):
        response = self.client.get(LIST_URL, {"search": "1234567"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["imo_number"], "1234567")

    def test_customer_filter_cannot_select_other_tenant_customer(self):
        response = self.client.get(LIST_URL, {"customer": self.other_customer.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class VesselCapabilityTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Cap Tenant", slug="cap-tenant")
        cls.user = User.objects.create(username="viewer", tenant=cls.tenant)
        sync_capabilities()
        provision_default_roles(cls.tenant)
        viewer_role = TenantRole.objects.get(tenant=cls.tenant, name="Viewer")
        UserRoleAssignment.objects.create(user=cls.user, role=viewer_role)
        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Test Co")
        cls.vessel = Vessel.objects.create(
            tenant=cls.tenant, customer=cls.customer,
            name="MV Test", imo_number="0000001",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_viewer_can_list(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create(self):
        response = self.client.post(LIST_URL, {
            "customer": self.customer.id,
            "name": "Blocked",
            "imo_number": "0000002",
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_update(self):
        response = self.client.patch(detail_url(self.vessel.id), {"name": "Blocked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class VesselIMORaceConditionTests(APITestCase):
    """Verify that a concurrent duplicate IMO returns 400, not 500."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Race Tenant", slug="race-tenant")
        cls.user = User.objects.create(username="race-user", tenant=cls.tenant)
        grant_all_capabilities(cls.user)
        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Race Co")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_db_constraint_duplicate_returns_400(self):
        Vessel.objects.create(
            tenant=self.tenant, customer=self.customer,
            name="MV First", imo_number="RACE001",
        )
        response = self.client.post(LIST_URL, {
            "customer": self.customer.id,
            "name": "MV Second",
            "imo_number": "RACE001",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("imo_number", response.data)

    def test_database_constraint_is_per_tenant(self):
        Vessel.objects.create(
            tenant=self.tenant, customer=self.customer,
            name="MV First", imo_number="DB-UNIQUE",
        )
        other_tenant = Tenant.objects.create(name="Other Race Tenant", slug="other-race-tenant")
        other_customer = Customer.objects.create(tenant=other_tenant, name="Other Race Co")
        other_vessel = Vessel.objects.create(
            tenant=other_tenant, customer=other_customer,
            name="MV Other Tenant", imo_number="DB-UNIQUE",
        )
        self.assertEqual(other_vessel.imo_number, "DB-UNIQUE")
        with self.assertRaises(IntegrityError):
            Vessel.objects.create(
                tenant=self.tenant, customer=self.customer,
                name="MV Duplicate", imo_number="DB-UNIQUE",
            )

    def test_integrity_error_from_concurrent_create_is_a_controlled_400(self):
        with patch("vessels.views.VesselSerializer.save", side_effect=IntegrityError("unique_imo_per_tenant")):
            response = self.client.post(LIST_URL, {
                "customer": self.customer.id,
                "name": "MV Race Loser",
                "imo_number": "RACE-CONCURRENT",
            })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imo_number"], ["A vessel with this IMO number already exists."])
