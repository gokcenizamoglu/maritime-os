"""
Security tests for the internal staff authentication endpoints
(users/views.py) — CSRF bootstrap, login, logout, me. See
docs/AUTHENTICATION_ARCHITECTURE.md for the full BFF flow these
endpoints implement.

Uses `APIClient(enforce_csrf_checks=True)` specifically where CSRF
behavior is being verified — DRF's default test client (like Django's)
disables CSRF checks, which would make every "CSRF should reject this"
test a false negative that passes for the wrong reason.
"""
import base64

from django.contrib.sessions.models import Session
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from tenants.models import Tenant
from users.models import User

CSRF_URL = "/api/auth/csrf/"
LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/auth/me/"


def _csrf_login(client: APIClient, username: str, password: str):
    """
    Shared helper: bootstrap CSRF, then log in with it — the exact
    sequence the Next.js BFF performs (see
    frontend/src/lib/auth/backend-auth.ts::performLogin), reused here so
    every test exercises the real flow rather than a shortcut.
    """
    csrf_response = client.get(CSRF_URL)
    token = csrf_response.data["csrfToken"]
    return client.post(LOGIN_URL, {"username": username, "password": password}, format="json", HTTP_X_CSRFTOKEN=token)


class CsrfBootstrapTests(APITestCase):
    def test_returns_a_masked_token(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.get(CSRF_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data.get("csrfToken"), str)
        self.assertGreater(len(response.data["csrfToken"]), 0)

    def test_establishes_a_usable_pre_auth_session(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get(CSRF_URL)
        # The session Django just issued is immediately usable for a
        # second bootstrap call — proves it's a real, persisted session,
        # not a one-shot token unattached to anything.
        response = client.get(CSRF_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reuses_the_existing_pre_auth_session_rather_than_rotating_it(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get(CSRF_URL)
        first_key = client.session.session_key
        client.get(CSRF_URL)
        second_key = client.session.session_key
        self.assertEqual(first_key, second_key)


class LoginTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine-auth")
        cls.user = User.objects.create_user(
            username="ops-user", password="correct-horse-battery-staple", tenant=cls.tenant,
        )
        cls.inactive_user = User.objects.create_user(
            username="inactive-user", password="whatever12345", tenant=cls.tenant, is_active=False,
        )
        cls.tenantless_user = User.objects.create_user(username="tenantless-user", password="whatever12345")
        cls.superuser = User.objects.create_superuser(
            username="admin", password="whatever12345", email="admin@example.com",
        )

    def test_valid_credentials_create_a_session(self):
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Session.objects.filter(session_key=client.session.session_key).exists())
        self.assertEqual(int(client.session["_auth_user_id"]), self.user.id)

    def test_invalid_password_returns_a_generic_failure(self):
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "ops-user", "wrong-password")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid credentials.")

    def test_unknown_username_returns_the_same_generic_failure(self):
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "no-such-user", "whatever")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid credentials.")

    def test_inactive_user_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "inactive-user", "whatever12345")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tenantless_non_superuser_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "tenantless-user", "whatever12345")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tenantless_superuser_is_allowed_to_authenticate(self):
        # Login itself must succeed — credentials are valid, and
        # User.tenant is documented as nullable specifically for
        # superusers (users/models.py). This does NOT mean the
        # superuser can use tenant-scoped endpoints: IsTenantMember
        # still rejects them there, completely unchanged by this
        # sprint — see config/permissions.py.
        client = APIClient(enforce_csrf_checks=True)
        response = _csrf_login(client, "admin", "whatever12345")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["tenant"])

    def test_session_key_rotates_on_login(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get(CSRF_URL)
        pre_login_key = client.session.session_key
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        post_login_key = client.session.session_key
        self.assertIsNotNone(pre_login_key)
        self.assertIsNotNone(post_login_key)
        self.assertNotEqual(pre_login_key, post_login_key)

    def test_pre_login_csrf_token_is_not_valid_after_login(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_response = client.get(CSRF_URL)
        pre_login_token = csrf_response.data["csrfToken"]
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        # Login rotates the session (and, under CSRF_USE_SESSIONS, the
        # CSRF secret tied to it) — reusing the OLD token for a
        # subsequent unsafe request must fail, proving the rotation is
        # real and not silently bypassed.
        response = client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=pre_login_token)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_without_csrf_token_is_rejected(self):
        # Regression test for a real bug found and fixed while building
        # this endpoint: DRF's APIView auto-applies csrf_exempt, and
        # SessionAuthentication.enforce_csrf() only runs for an ALREADY
        # authenticated request — neither covers a pre-login POST, so
        # without the explicit @method_decorator(csrf_protect, ...) on
        # LoginView, this request would have succeeded with no CSRF
        # token at all.
        client = APIClient(enforce_csrf_checks=True)
        client.get(CSRF_URL)
        response = client.post(
            LOGIN_URL, {"username": "ops-user", "password": "correct-horse-battery-staple"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MeTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine-me")
        cls.other_tenant = Tenant.objects.create(name="Other Co", slug="other-co-me")
        cls.user = User.objects.create_user(
            username="ops-user", password="correct-horse-battery-staple", tenant=cls.tenant,
            first_name="Ops", last_name="User",
        )
        cls.other_user = User.objects.create_user(
            username="other-user", password="whatever12345", tenant=cls.other_tenant,
        )
        cls.superuser = User.objects.create_superuser(
            username="admin", password="whatever12345", email="admin@example.com",
        )

    def test_unauthenticated_is_rejected(self):
        client = APIClient()
        response = client.get(ME_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_authenticated_returns_only_the_caller(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        response = client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["username"], "ops-user")
        self.assertNotEqual(response.data["id"], self.other_user.id)

    def test_correct_tenant_is_returned(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        response = client.get(ME_URL)
        self.assertEqual(response.data["tenant"], {"id": self.tenant.id, "name": self.tenant.name})

    def test_no_sensitive_or_unrelated_fields_are_exposed(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        response = client.get(ME_URL)
        self.assertEqual(
            set(response.data.keys()),
            {"id", "username", "first_name", "last_name", "role", "tenant"},
        )
        self.assertNotIn("password", response.data)

    def test_superuser_tenant_is_explicitly_null_not_omitted(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "admin", "whatever12345")
        response = client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tenant", response.data)
        self.assertIsNone(response.data["tenant"])


class LogoutTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine-logout")
        cls.user = User.objects.create_user(
            username="ops-user", password="correct-horse-battery-staple", tenant=cls.tenant,
        )

    def test_requires_authentication(self):
        client = APIClient()
        response = client.post(LOGOUT_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_requires_valid_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        response = client.post(LOGOUT_URL)  # no X-CSRFToken
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalidates_the_real_session(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        session_key = client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())

        token = client.get(CSRF_URL).data["csrfToken"]
        response = client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    def test_old_session_credential_fails_after_logout(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        token = client.get(CSRF_URL).data["csrfToken"]
        client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)

        response = client.get(ME_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class SessionAuthenticationConfigurationTests(APITestCase):
    """
    Verifies the explicit DRF settings from this sprint (settings.py):
    SessionAuthentication only, BasicAuthentication removed.
    """
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine-sessionauth")
        cls.user = User.objects.create_user(
            username="ops-user", password="correct-horse-battery-staple", tenant=cls.tenant,
        )

    def test_unsafe_session_authenticated_request_without_csrf_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        response = client.post(LOGOUT_URL)  # authenticated, but no CSRF token
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_correct_csrf_token_allows_the_request_through(self):
        client = APIClient(enforce_csrf_checks=True)
        _csrf_login(client, "ops-user", "correct-horse-battery-staple")
        token = client.get(CSRF_URL).data["csrfToken"]
        response = client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_basic_authentication_credentials_are_no_longer_accepted(self):
        client = APIClient()
        credentials = base64.b64encode(b"ops-user:correct-horse-battery-staple").decode()
        response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Basic {credentials}")
        # SessionAuthentication is the ONLY configured authentication
        # class (settings.py) now — valid Basic credentials must NOT
        # authenticate the request; it must be rejected exactly as if
        # no credentials were sent at all.
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
