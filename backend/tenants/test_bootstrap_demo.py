from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from authorization.models import Capability, TenantRole, UserRoleAssignment
from authorization.services import CrossTenantAssignmentError
from tenants.models import Tenant


@override_settings(DEBUG=True)
class BootstrapDemoCommandTests(TestCase):
    def run_command(self, *args):
        output = StringIO()
        call_command("bootstrap_demo", *args, stdout=output)
        return output.getvalue()

    def test_first_run_creates_demo_tenant_user_roles_and_assignment(self):
        output = self.run_command("--password", "first-local-password")

        tenant = Tenant.objects.get(slug="demo")
        user = get_user_model().objects.get(username="demo")
        role = TenantRole.objects.get(tenant=tenant, name="Tenant Admin")
        self.assertEqual(user.tenant_id, tenant.id)
        self.assertEqual(user.role, get_user_model().Role.ADMIN)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("first-local-password"))
        self.assertTrue(
            UserRoleAssignment.objects.filter(user=user, role=role).exists()
        )
        self.assertGreater(Capability.objects.count(), 0)
        self.assertIn("Demo tenant created", output)
        self.assertNotIn("first-local-password", output)

    def test_second_run_is_idempotent_and_does_not_silently_reset_password(self):
        self.run_command("--password", "original-local-password")
        counts_before = {
            "tenant": Tenant.objects.count(),
            "user": get_user_model().objects.count(),
            "role": TenantRole.objects.count(),
            "assignment": UserRoleAssignment.objects.count(),
            "capability": Capability.objects.count(),
        }

        output = self.run_command("--password", "ignored-new-password")

        counts_after = {
            "tenant": Tenant.objects.count(),
            "user": get_user_model().objects.count(),
            "role": TenantRole.objects.count(),
            "assignment": UserRoleAssignment.objects.count(),
            "capability": Capability.objects.count(),
        }
        user = get_user_model().objects.get(username="demo")
        self.assertEqual(counts_after, counts_before)
        self.assertTrue(user.check_password("original-local-password"))
        self.assertFalse(user.check_password("ignored-new-password"))
        self.assertIn("password was ignored", output)

    def test_password_reset_requires_explicit_flag(self):
        self.run_command("--password", "original-local-password")

        self.run_command(
            "--password",
            "explicit-new-password",
            "--reset-password",
        )

        user = get_user_model().objects.get(username="demo")
        self.assertTrue(user.check_password("explicit-new-password"))
        self.assertFalse(user.check_password("original-local-password"))

    @override_settings(DEBUG=False)
    def test_command_is_blocked_in_production_like_settings(self):
        counts_before = {
            "capability": Capability.objects.count(),
            "role": TenantRole.objects.count(),
            "assignment": UserRoleAssignment.objects.count(),
        }
        with self.assertRaisesMessage(
            CommandError,
            "bootstrap_demo is disabled when DEBUG is False.",
        ):
            self.run_command()

        self.assertFalse(Tenant.objects.filter(slug="demo").exists())
        self.assertFalse(get_user_model().objects.filter(username="demo").exists())
        self.assertEqual(Capability.objects.count(), counts_before["capability"])
        self.assertEqual(TenantRole.objects.count(), counts_before["role"])
        self.assertEqual(
            UserRoleAssignment.objects.count(),
            counts_before["assignment"],
        )

    def test_existing_platform_staff_account_is_never_reused_as_demo_user(self):
        tenant = Tenant.objects.create(name="Existing Demo", slug="demo")
        staff_user = get_user_model().objects.create_user(
            username="demo",
            password="platform-staff-password",
            tenant=tenant,
            is_staff=True,
        )
        counts_before = {
            "role": TenantRole.objects.count(),
            "assignment": UserRoleAssignment.objects.count(),
        }

        with self.assertRaisesMessage(
            CommandError,
            "User 'demo' is a platform staff account",
        ):
            self.run_command(
                "--password",
                "replacement-password",
                "--reset-password",
            )

        staff_user.refresh_from_db()
        self.assertTrue(staff_user.is_staff)
        self.assertTrue(staff_user.check_password("platform-staff-password"))
        self.assertFalse(staff_user.check_password("replacement-password"))
        self.assertEqual(TenantRole.objects.count(), counts_before["role"])
        self.assertEqual(
            UserRoleAssignment.objects.count(),
            counts_before["assignment"],
        )

    def test_failure_rolls_back_all_bootstrap_writes(self):
        counts_before = {
            "capability": Capability.objects.count(),
            "role": TenantRole.objects.count(),
            "assignment": UserRoleAssignment.objects.count(),
        }
        with patch(
            "tenants.management.commands.bootstrap_demo.assign_role",
            side_effect=CrossTenantAssignmentError("forced assignment failure"),
        ):
            with self.assertRaisesMessage(CommandError, "forced assignment failure"):
                self.run_command("--password", "rolled-back-password")

        self.assertFalse(Tenant.objects.filter(slug="demo").exists())
        self.assertFalse(get_user_model().objects.filter(username="demo").exists())
        self.assertEqual(Capability.objects.count(), counts_before["capability"])
        self.assertEqual(TenantRole.objects.count(), counts_before["role"])
        self.assertEqual(
            UserRoleAssignment.objects.count(),
            counts_before["assignment"],
        )
