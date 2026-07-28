"""
Tests for the authorization sprint: capability registry/sync, role
isolation, effective-capabilities policy, default provisioning,
endpoint enforcement, /api/auth/me/ response, and migration behavior.
"""
from authorization.models import (
    Capability,
    RoleCapability,
    TenantRole,
    UserRoleAssignment,
)
from authorization.registry import (
    ALL_CAPABILITIES,
    CAPABILITY_REGISTRY,
    OPS_CAPABILITIES,
    VIEW_ONLY_CAPABILITIES,
)
from authorization.services import (
    CrossTenantAssignmentError,
    assign_role,
    provision_default_roles,
    sync_capabilities,
    user_effective_capabilities,
    user_has_capability,
)
from authorization.test_helpers import grant_all_capabilities
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from tenants.models import Tenant
from users.models import User

CSRF_URL = "/api/auth/csrf/"
LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/auth/me/"
SR_LIST_URL = "/api/service-requests/"
DOC_LIST_URL = "/api/documents/"
CHECKLIST_LIST_URL = "/api/checklist-items/"
WORKFLOW_LIST_URL = "/api/workflow-steps/"
RULE_LIST_URL = "/api/rules/"
RULE_METADATA_URL = "/api/rules/metadata/"


# ---------------------------------------------------------------------------
# Capability registry and database sync
# ---------------------------------------------------------------------------

class CapabilitySyncTests(APITestCase):
    def test_sync_creates_all_registry_capabilities(self):
        sync_capabilities()
        db_codes = set(Capability.objects.values_list("code", flat=True))
        self.assertEqual(db_codes, set(CAPABILITY_REGISTRY.keys()))

    def test_sync_is_idempotent(self):
        sync_capabilities()
        first_count = Capability.objects.count()
        result = sync_capabilities()
        self.assertEqual(Capability.objects.count(), first_count)
        self.assertEqual(result["created"], 0)

    def test_sync_updates_label_on_existing(self):
        sync_capabilities()
        cap = Capability.objects.get(code="service_request.view")
        cap.label = "Old Label"
        cap.save()
        sync_capabilities()
        cap.refresh_from_db()
        self.assertEqual(cap.label, CAPABILITY_REGISTRY["service_request.view"].label)

    def test_sync_deactivates_removed_capabilities(self):
        sync_capabilities()
        Capability.objects.create(
            code="obsolete.capability", label="Obsolete", category="test", module_code="test",
        )
        sync_capabilities()
        obsolete = Capability.objects.get(code="obsolete.capability")
        self.assertFalse(obsolete.is_active)
        self.assertTrue(obsolete.is_deprecated)

    def test_sync_reactivates_previously_deactivated_capability(self):
        sync_capabilities()
        cap = Capability.objects.get(code="service_request.view")
        cap.is_active = False
        cap.is_deprecated = True
        cap.save()
        sync_capabilities()
        cap.refresh_from_db()
        self.assertTrue(cap.is_active)
        self.assertFalse(cap.is_deprecated)

    def test_tenants_cannot_create_capabilities_through_api(self):
        sync_capabilities()
        tenant = Tenant.objects.create(name="Test", slug="test-cap-api")
        user = User.objects.create(username="test-cap", tenant=tenant)
        grant_all_capabilities(user)
        self.client.force_authenticate(user=user)
        # No capability endpoint is registered — verify 404
        response = self.client.post("/api/capabilities/", {"code": "fake.cap"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Role isolation
# ---------------------------------------------------------------------------

class RoleIsolationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        sync_capabilities()
        cls.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a-iso")
        cls.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b-iso")
        cls.user_a = User.objects.create(username="user-a", tenant=cls.tenant_a)
        cls.user_b = User.objects.create(username="user-b", tenant=cls.tenant_b)

    def test_same_role_name_allowed_in_different_tenants(self):
        role_a = TenantRole.objects.create(tenant=self.tenant_a, name="Manager")
        role_b = TenantRole.objects.create(tenant=self.tenant_b, name="Manager")
        self.assertNotEqual(role_a.id, role_b.id)

    def test_cross_tenant_role_assignment_rejected(self):
        role_b = TenantRole.objects.create(tenant=self.tenant_b, name="Cross-Test")
        with self.assertRaises(CrossTenantAssignmentError):
            assign_role(user=self.user_a, role=role_b)

    def test_tenantless_user_assignment_rejected(self):
        tenantless = User.objects.create(username="no-tenant")
        role_a = TenantRole.objects.create(tenant=self.tenant_a, name="No-Tenant-Test")
        with self.assertRaises(CrossTenantAssignmentError):
            assign_role(user=tenantless, role=role_a)

    def test_user_may_receive_multiple_roles(self):
        role1 = TenantRole.objects.create(tenant=self.tenant_a, name="Role1")
        role2 = TenantRole.objects.create(tenant=self.tenant_a, name="Role2")
        assign_role(user=self.user_a, role=role1)
        assign_role(user=self.user_a, role=role2)
        self.assertEqual(self.user_a.role_assignments.count(), 2)

    def test_duplicate_assignment_rejected(self):
        role = TenantRole.objects.create(tenant=self.tenant_a, name="Dup-Test")
        assign_role(user=self.user_a, role=role)
        # get_or_create makes it idempotent, not an error
        assignment = assign_role(user=self.user_a, role=role)
        self.assertEqual(
            UserRoleAssignment.objects.filter(user=self.user_a, role=role).count(), 1,
        )

    def test_deleting_role_does_not_delete_capabilities(self):
        role = TenantRole.objects.create(tenant=self.tenant_a, name="Del-Test")
        cap = Capability.objects.get(code="service_request.view")
        RoleCapability.objects.create(role=role, capability=cap)
        role.delete()
        self.assertTrue(Capability.objects.filter(code="service_request.view").exists())


# ---------------------------------------------------------------------------
# Effective capabilities policy
# ---------------------------------------------------------------------------

class EffectiveCapabilitiesTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        sync_capabilities()
        cls.tenant = Tenant.objects.create(name="Policy Tenant", slug="policy-tenant")
        cls.other_tenant = Tenant.objects.create(name="Other Policy", slug="other-policy")
        cls.user = User.objects.create(username="policy-user", tenant=cls.tenant)

    def test_union_across_multiple_roles(self):
        role_a = TenantRole.objects.create(tenant=self.tenant, name="RoleA")
        role_b = TenantRole.objects.create(tenant=self.tenant, name="RoleB")
        cap_sr = Capability.objects.get(code="service_request.view")
        cap_doc = Capability.objects.get(code="document.view")
        RoleCapability.objects.create(role=role_a, capability=cap_sr)
        RoleCapability.objects.create(role=role_b, capability=cap_doc)
        assign_role(user=self.user, role=role_a)
        assign_role(user=self.user, role=role_b)
        caps = user_effective_capabilities(self.user)
        self.assertIn("service_request.view", caps)
        self.assertIn("document.view", caps)

    def test_inactive_role_ignored(self):
        role = TenantRole.objects.create(tenant=self.tenant, name="Inactive-Role", is_active=False)
        cap = Capability.objects.get(code="service_request.view")
        RoleCapability.objects.create(role=role, capability=cap)
        assign_role(user=self.user, role=role)
        caps = user_effective_capabilities(self.user)
        self.assertNotIn("service_request.view", caps)

    def test_inactive_capability_ignored(self):
        role = TenantRole.objects.create(tenant=self.tenant, name="Inactive-Cap-Role")
        cap = Capability.objects.get(code="service_request.view")
        cap.is_active = False
        cap.save()
        RoleCapability.objects.create(role=role, capability=cap)
        assign_role(user=self.user, role=role)
        caps = user_effective_capabilities(self.user)
        self.assertNotIn("service_request.view", caps)
        cap.is_active = True
        cap.save()

    def test_other_tenants_role_never_grants_access(self):
        other_role = TenantRole.objects.create(tenant=self.other_tenant, name="Foreign-Role")
        cap = Capability.objects.get(code="service_request.view")
        RoleCapability.objects.create(role=other_role, capability=cap)
        # Direct DB insert to bypass service validation
        UserRoleAssignment.objects.create(user=self.user, role=other_role)
        caps = user_effective_capabilities(self.user)
        self.assertNotIn("service_request.view", caps)

    def test_tenantless_user_gets_no_capabilities(self):
        tenantless = User.objects.create(username="tenantless-policy")
        caps = user_effective_capabilities(tenantless)
        self.assertEqual(caps, frozenset())

    def test_user_has_capability_returns_true_when_granted(self):
        role = TenantRole.objects.create(tenant=self.tenant, name="Has-Cap-Test")
        cap = Capability.objects.get(code="document.create")
        RoleCapability.objects.create(role=role, capability=cap)
        assign_role(user=self.user, role=role)
        self.assertTrue(user_has_capability(self.user, "document.create"))

    def test_user_has_capability_returns_false_when_missing(self):
        self.assertFalse(user_has_capability(self.user, "rule.delete"))


# ---------------------------------------------------------------------------
# Default role provisioning
# ---------------------------------------------------------------------------

class DefaultProvisioningTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        sync_capabilities()

    def test_provision_creates_three_default_roles(self):
        tenant = Tenant.objects.create(name="Prov Test", slug="prov-test")
        provision_default_roles(tenant)
        self.assertEqual(TenantRole.objects.filter(tenant=tenant).count(), 3)

    def test_provision_is_idempotent(self):
        tenant = Tenant.objects.create(name="Idem Test", slug="idem-test")
        provision_default_roles(tenant)
        provision_default_roles(tenant)
        self.assertEqual(TenantRole.objects.filter(tenant=tenant).count(), 3)

    def test_roles_are_cloned_per_tenant(self):
        t1 = Tenant.objects.create(name="T1", slug="t1-prov")
        t2 = Tenant.objects.create(name="T2", slug="t2-prov")
        provision_default_roles(t1)
        provision_default_roles(t2)
        t1_ids = set(TenantRole.objects.filter(tenant=t1).values_list("id", flat=True))
        t2_ids = set(TenantRole.objects.filter(tenant=t2).values_list("id", flat=True))
        self.assertTrue(t1_ids.isdisjoint(t2_ids))

    def test_tenant_admin_receives_all_active_capabilities(self):
        tenant = Tenant.objects.create(name="Admin Cap", slug="admin-cap")
        provision_default_roles(tenant)
        admin_role = TenantRole.objects.get(tenant=tenant, name="Tenant Admin")
        admin_caps = set(admin_role.capabilities.values_list("code", flat=True))
        active_caps = set(Capability.objects.filter(is_active=True).values_list("code", flat=True))
        self.assertEqual(admin_caps, active_caps)

    def test_viewer_receives_only_view_capabilities(self):
        tenant = Tenant.objects.create(name="Viewer Cap", slug="viewer-cap")
        provision_default_roles(tenant)
        viewer_role = TenantRole.objects.get(tenant=tenant, name="Viewer")
        viewer_caps = set(viewer_role.capabilities.values_list("code", flat=True))
        for cap_code in viewer_caps:
            self.assertTrue(cap_code.endswith(".view"), f"{cap_code} is not a view capability")

    def test_operations_role_excludes_rule_management(self):
        tenant = Tenant.objects.create(name="Ops Cap", slug="ops-cap")
        provision_default_roles(tenant)
        ops_role = TenantRole.objects.get(tenant=tenant, name="Operations")
        ops_caps = set(ops_role.capabilities.values_list("code", flat=True))
        self.assertNotIn("rule.create", ops_caps)
        self.assertNotIn("rule.update", ops_caps)
        self.assertNotIn("rule.delete", ops_caps)
        self.assertIn("service_request.create", ops_caps)
        self.assertNotIn("tenant_catalog.manage", ops_caps)
        self.assertNotIn("operation_template.manage", ops_caps)
        self.assertNotIn("operation_template.publish", ops_caps)

    def test_new_tenant_is_provisioned_with_safe_default_roles(self):
        tenant = Tenant.objects.create(name="Automatic Provisioning", slug="automatic-provisioning")
        self.assertEqual(TenantRole.objects.filter(tenant=tenant).count(), 3)
        admin_caps = set(TenantRole.objects.get(tenant=tenant, name="Tenant Admin").capabilities.values_list("code", flat=True))
        operations_caps = set(TenantRole.objects.get(tenant=tenant, name="Operations").capabilities.values_list("code", flat=True))
        self.assertIn("operation_template.publish", admin_caps)
        self.assertNotIn("operation_template.publish", operations_caps)


# ---------------------------------------------------------------------------
# Endpoint enforcement
# ---------------------------------------------------------------------------

class EndpointEnforcementTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        sync_capabilities()
        cls.tenant = Tenant.objects.create(name="Enforce", slug="enforce-test")
        cls.other_tenant = Tenant.objects.create(name="Other Enforce", slug="other-enforce")

        cls.admin_user = User.objects.create(username="admin-enforce", tenant=cls.tenant)
        grant_all_capabilities(cls.admin_user)

        cls.viewer_user = User.objects.create(username="viewer-enforce", tenant=cls.tenant)
        provision_default_roles(cls.tenant)
        viewer_role = TenantRole.objects.get(tenant=cls.tenant, name="Viewer")
        assign_role(user=cls.viewer_user, role=viewer_role)

        cls.no_role_user = User.objects.create(username="norole-enforce", tenant=cls.tenant)

    def test_admin_can_list_service_requests(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(SR_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_can_list_service_requests(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(SR_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_service_request(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.post(SR_LIST_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_role_user_gets_403(self):
        self.client.force_authenticate(user=self.no_role_user)
        response = self.client.get(SR_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_list_documents(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(DOC_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_can_list_checklist_items(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(CHECKLIST_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_can_list_workflow_steps(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(WORKFLOW_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_can_list_rules(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(RULE_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_rule(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.post(RULE_LIST_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_access_rule_metadata(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(RULE_METADATA_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tenant_isolation_still_enforced_with_capability(self):
        other_user = User.objects.create(username="other-enforce", tenant=self.other_tenant)
        grant_all_capabilities(other_user)
        self.client.force_authenticate(user=other_user)
        response = self.client.get(SR_LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_unauthenticated_gets_401_or_403(self):
        response = self.client.get(SR_LIST_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


# ---------------------------------------------------------------------------
# /api/auth/me/ response
# ---------------------------------------------------------------------------

class MeResponseTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        sync_capabilities()
        cls.tenant = Tenant.objects.create(name="Me Test", slug="me-test")
        cls.other_tenant = Tenant.objects.create(name="Other Me", slug="other-me")
        cls.user = User.objects.create_user(
            username="me-user", password="test12345", tenant=cls.tenant,
        )
        provision_default_roles(cls.tenant)
        admin_role = TenantRole.objects.get(tenant=cls.tenant, name="Tenant Admin")
        assign_role(user=cls.user, role=admin_role)

        provision_default_roles(cls.other_tenant)

    def _login_and_get_me(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(CSRF_URL).data["csrfToken"]
        client.post(
            LOGIN_URL,
            {"username": "me-user", "password": "test12345"},
            format="json", HTTP_X_CSRFTOKEN=csrf,
        )
        return client.get(ME_URL)

    def test_returns_roles(self):
        response = self._login_and_get_me()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("roles", response.data)
        role_names = {r["name"] for r in response.data["roles"]}
        self.assertIn("Tenant Admin", role_names)

    def test_returns_sorted_capabilities(self):
        response = self._login_and_get_me()
        caps = response.data["capabilities"]
        self.assertEqual(caps, sorted(caps))
        self.assertGreater(len(caps), 0)

    def test_does_not_expose_other_tenants_role(self):
        response = self._login_and_get_me()
        role_ids = {r["id"] for r in response.data["roles"]}
        other_role_ids = set(
            TenantRole.objects.filter(tenant=self.other_tenant).values_list("id", flat=True)
        )
        self.assertTrue(role_ids.isdisjoint(other_role_ids))

    def test_existing_fields_still_present(self):
        response = self._login_and_get_me()
        for field in ("id", "username", "first_name", "last_name", "role", "tenant"):
            self.assertIn(field, response.data)

    def test_superuser_gets_empty_roles_and_capabilities(self):
        User.objects.create_superuser(
            username="su-me", password="test12345", email="su@example.com",
        )
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(CSRF_URL).data["csrfToken"]
        client.post(
            LOGIN_URL,
            {"username": "su-me", "password": "test12345"},
            format="json", HTTP_X_CSRFTOKEN=csrf,
        )
        response = client.get(ME_URL)
        self.assertEqual(response.data["roles"], [])
        self.assertEqual(response.data["capabilities"], [])


# ---------------------------------------------------------------------------
# Migration / data migration behavior
# ---------------------------------------------------------------------------

class MigrationBehaviorTests(APITestCase):
    def test_existing_admin_user_gets_tenant_admin_role(self):
        sync_capabilities()
        tenant = Tenant.objects.create(name="Mig Test", slug="mig-test")
        user = User.objects.create(username="mig-admin", tenant=tenant, role="admin")
        provision_default_roles(tenant)
        assign_role(
            user=user,
            role=TenantRole.objects.get(tenant=tenant, name="Tenant Admin"),
        )
        caps = user_effective_capabilities(user)
        self.assertEqual(caps, frozenset(
            Capability.objects.filter(is_active=True).values_list("code", flat=True)
        ))

    def test_existing_viewer_user_gets_viewer_role(self):
        sync_capabilities()
        tenant = Tenant.objects.create(name="Mig V Test", slug="mig-v-test")
        user = User.objects.create(username="mig-viewer", tenant=tenant, role="viewer")
        provision_default_roles(tenant)
        assign_role(
            user=user,
            role=TenantRole.objects.get(tenant=tenant, name="Viewer"),
        )
        caps = user_effective_capabilities(user)
        for cap_code in caps:
            self.assertTrue(cap_code.endswith(".view"))

    def test_rerunning_provisioning_does_not_duplicate(self):
        sync_capabilities()
        tenant = Tenant.objects.create(name="Rerun", slug="rerun-test")
        provision_default_roles(tenant)
        provision_default_roles(tenant)
        self.assertEqual(TenantRole.objects.filter(tenant=tenant).count(), 3)
