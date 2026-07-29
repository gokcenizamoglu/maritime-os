from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from authorization.models import TenantRole
from authorization.services import (
    CrossTenantAssignmentError,
    assign_role,
    provision_default_roles,
    sync_capabilities,
)
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create or reuse a local demo tenant and application user, then assign "
        "the tenant's Tenant Admin capability role. This command is blocked "
        "when DEBUG is disabled."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-name",
            default="MaritimeOS Demo",
            help="Display name used only when the demo tenant is first created.",
        )
        parser.add_argument(
            "--tenant-slug",
            default="demo",
            help="Stable slug used to find or create the demo tenant.",
        )
        parser.add_argument(
            "--username",
            default="demo",
            help="Username used to find or create the demo application user.",
        )
        parser.add_argument(
            "--email",
            default="demo@example.test",
            help="Email used only when the demo user is first created.",
        )
        parser.add_argument(
            "--password",
            help=(
                "Password for a new user, or for an existing user when combined "
                "with --reset-password. If omitted, a random local password is generated."
            ),
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Explicitly replace an existing demo user's password.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("bootstrap_demo is disabled when DEBUG is False.")

        try:
            with transaction.atomic():
                result = self._bootstrap(**options)
        except CrossTenantAssignmentError as exc:
            raise CommandError(str(exc)) from exc

        self._report(result)

    def _bootstrap(
        self,
        *,
        tenant_name,
        tenant_slug,
        username,
        email,
        password,
        reset_password,
        **_options,
    ):
        capability_summary = sync_capabilities()
        tenant, tenant_created = Tenant.objects.get_or_create(
            slug=tenant_slug,
            defaults={"name": tenant_name, "is_active": True},
        )
        if not tenant.is_active:
            raise CommandError(
                f"Tenant '{tenant.slug}' exists but is inactive; it was not modified."
            )

        role_summary = provision_default_roles(tenant)
        User = get_user_model()
        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "tenant": tenant,
                "role": User.Role.ADMIN,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if not user_created and user.tenant_id != tenant.id:
            raise CommandError(
                f"User '{username}' already belongs to another tenant; it was not modified."
            )
        if not user_created and (user.is_staff or user.is_superuser):
            raise CommandError(
                f"User '{username}' is a platform staff account; choose a different "
                "demo username."
            )
        if not user.is_active:
            raise CommandError(
                f"User '{username}' exists but is inactive; it was not modified."
            )

        password_changed = user_created or reset_password
        generated_password = None
        if password_changed:
            effective_password = password or get_random_string(24)
            user.set_password(effective_password)
            user.save(update_fields=["password"])
            if password is None:
                generated_password = effective_password

        role = TenantRole.objects.get(tenant=tenant, name="Tenant Admin")
        assignment = assign_role(user=user, role=role)

        return {
            "tenant": tenant,
            "tenant_created": tenant_created,
            "user": user,
            "user_created": user_created,
            "assignment": assignment,
            "capability_summary": capability_summary,
            "role_summary": role_summary,
            "password_changed": password_changed,
            "generated_password": generated_password,
            "ignored_password": bool(password and not password_changed),
        }

    def _report(self, result):
        tenant_action = "created" if result["tenant_created"] else "reused"
        user_action = "created" if result["user_created"] else "reused"
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo tenant {tenant_action}: {result['tenant'].name} "
                f"({result['tenant'].slug})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo application user {user_action}: {result['user'].username}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Role assignment ready: {result['assignment'].role.name}"
            )
        )
        self.stdout.write(
            "Capability sync: "
            f"{result['capability_summary']['created']} created, "
            f"{result['capability_summary']['updated']} updated, "
            f"{result['capability_summary']['deactivated']} deactivated."
        )
        self.stdout.write(
            "Default roles: "
            f"{result['role_summary']['created']} created, "
            f"{result['role_summary']['updated']} reused."
        )
        if result["generated_password"]:
            self.stdout.write(
                self.style.WARNING(
                    "Generated local password (shown once): "
                    f"{result['generated_password']}"
                )
            )
        elif result["password_changed"]:
            self.stdout.write("The supplied password was applied.")
        elif result["ignored_password"]:
            self.stdout.write(
                self.style.WARNING(
                    "The supplied password was ignored for the existing user. "
                    "Use --reset-password to change it explicitly."
                )
            )
        else:
            self.stdout.write("The existing user's password was left unchanged.")
