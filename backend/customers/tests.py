from authorization.test_helpers import grant_all_capabilities
from authorization.models import TenantRole, UserRoleAssignment
from authorization.services import provision_default_roles, sync_capabilities
from rest_framework import status
from rest_framework.test import APITestCase
from customers.models import Customer
from tenants.models import Tenant
from users.models import User

LIST_URL = "/api/customers/"


def detail_url(pk):
    return f"/api/customers/{pk}/"


class CustomerCRUDTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine")
        cls.other_tenant = Tenant.objects.create(name="Other Co", slug="other-co")
        cls.user = User.objects.create(username="ops-user", tenant=cls.tenant)
        grant_all_capabilities(cls.user)

        cls.customer = Customer.objects.create(
            tenant=cls.tenant, name="Acme Shipping",
            contact_email="acme@example.com",
        )
        cls.other_customer = Customer.objects.create(
            tenant=cls.other_tenant, name="Other Shipping",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_own_tenant(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.customer.id, ids)
        self.assertNotIn(self.other_customer.id, ids)

    def test_list_has_paginated_envelope(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(set(response.data.keys()), {"count", "next", "previous", "results"})

    def test_retrieve_own_tenant(self):
        response = self.client.get(detail_url(self.customer.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Acme Shipping")

    def test_retrieve_cross_tenant_returns_404(self):
        response = self.client.get(detail_url(self.other_customer.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_customer(self):
        data = {"name": "New Customer", "contact_email": "new@example.com"}
        response = self.client.post(LIST_URL, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Customer")
        created = Customer.objects.get(id=response.data["id"])
        self.assertEqual(created.tenant_id, self.tenant.id)

    def test_create_assigns_user_tenant(self):
        data = {"name": "Auto Tenant Customer"}
        response = self.client.post(LIST_URL, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.get(id=response.data["id"]).tenant_id, self.tenant.id)

    def test_client_cannot_choose_customer_tenant(self):
        response = self.client.post(
            LIST_URL,
            {"name": "Server Tenant Wins", "tenant": self.other_tenant.id},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Customer.objects.get(id=response.data["id"])
        self.assertEqual(created.tenant_id, self.tenant.id)
        self.assertNotIn("tenant", response.data)

    def test_partial_update(self):
        response = self.client.patch(
            detail_url(self.customer.id),
            {"contact_phone": "+90 555 1234567"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.contact_phone, "+90 555 1234567")

    def test_cross_tenant_update_returns_404(self):
        response = self.client.patch(
            detail_url(self.other_customer.id),
            {"name": "Hacked"},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_not_allowed(self):
        response = self.client.delete(detail_url(self.customer.id))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_not_allowed(self):
        response = self.client.put(
            detail_url(self.customer.id),
            {"name": "Full Update"},
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_by_name(self):
        response = self.client.get(LIST_URL, {"search": "Acme"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Acme Shipping")

    def test_search_cannot_leak_other_tenant_customer(self):
        response = self.client.get(LIST_URL, {"search": "Other Shipping"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class CustomerCapabilityTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Cap Tenant", slug="cap-tenant")
        cls.user = User.objects.create(username="viewer", tenant=cls.tenant)
        sync_capabilities()
        provision_default_roles(cls.tenant)
        viewer_role = TenantRole.objects.get(tenant=cls.tenant, name="Viewer")
        UserRoleAssignment.objects.create(user=cls.user, role=viewer_role)
        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Test Co")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_viewer_can_list(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create(self):
        response = self.client.post(LIST_URL, {"name": "Blocked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_update(self):
        response = self.client.patch(detail_url(self.customer.id), {"name": "Blocked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_tenant_cannot_use_customer_api(self):
        self.tenant.is_active = False
        self.tenant.save(update_fields=["is_active"])
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
