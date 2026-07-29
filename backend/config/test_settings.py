import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_PREFIXES = ("DJANGO_", "POSTGRES_")
VALID_PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": (
        "A9!production-test-value-only_B8@with-enough-variety_C7#not-a-real-secret"
    ),
    "DJANGO_ALLOWED_HOSTS": "app.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.test",
    "DJANGO_HSTS_SECONDS": "3600",
    "POSTGRES_DB": "maritimeos",
    "POSTGRES_USER": "maritimeos",
    "POSTGRES_PASSWORD": "test-value-not-a-production-credential",
    "POSTGRES_HOST": "database.example.test",
    "POSTGRES_PORT": "5432",
    "POSTGRES_SSLMODE": "verify-full",
}


class SettingsProcessMixin:
    maxDiff = None

    def isolated_environment(
        self,
        module=None,
        *,
        environment=None,
        remove=(),
    ):
        isolated_environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(ENVIRONMENT_PREFIXES)
        }
        isolated_environment.update(
            {
                "DJANGO_LOAD_DOTENV": "false",
                "PYTHONPATH": str(BACKEND_ROOT),
            }
        )
        if module is not None:
            isolated_environment["DJANGO_SETTINGS_MODULE"] = module
        isolated_environment.update(environment or {})
        for name in remove:
            isolated_environment.pop(name, None)
        return isolated_environment

    def run_settings(
        self,
        module,
        source,
        *,
        environment=None,
        remove=(),
    ):
        isolated_environment = self.isolated_environment(
            module,
            environment=environment,
            remove=remove,
        )

        return subprocess.run(
            [sys.executable, "-c", source],
            cwd=BACKEND_ROOT,
            env=isolated_environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def run_manage(self, *arguments):
        return subprocess.run(
            [sys.executable, "manage.py", *arguments],
            cwd=BACKEND_ROOT,
            env=self.isolated_environment(),
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def assert_failed_with(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)


class EnvironmentSettingsTests(SettingsProcessMixin, SimpleTestCase):
    settings_snapshot = """
import json
from django.conf import settings
print(json.dumps({
    "debug": settings.DEBUG,
    "admin": settings.ADMIN_ENABLED,
    "engine": settings.DATABASES["default"]["ENGINE"],
    "hosts": settings.ALLOWED_HOSTS,
}))
"""

    def test_local_settings_use_postgresql_and_keep_admin_available(self):
        result = self.run_settings("config.settings.local", self.settings_snapshot)

        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertTrue(snapshot["debug"])
        self.assertTrue(snapshot["admin"])
        self.assertEqual(snapshot["engine"], "django.db.backends.postgresql")
        self.assertIn("localhost", snapshot["hosts"])

    def test_test_settings_use_postgresql_without_debug(self):
        result = self.run_settings("config.settings.test", self.settings_snapshot)

        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertFalse(snapshot["debug"])
        self.assertTrue(snapshot["admin"])
        self.assertEqual(snapshot["engine"], "django.db.backends.postgresql")

    def test_production_rejects_missing_secret_before_startup(self):
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.DEBUG)",
            environment=VALID_PRODUCTION_ENV,
            remove=("DJANGO_SECRET_KEY",),
        )

        self.assert_failed_with(result, "DJANGO_SECRET_KEY")

    def test_production_rejects_missing_database_configuration(self):
        required_names = (
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_SSLMODE",
        )
        for name in required_names:
            with self.subTest(name=name):
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.DATABASES)",
                    environment=VALID_PRODUCTION_ENV,
                    remove=(name,),
                )
                self.assert_failed_with(result, name)

    def test_production_preserves_nonempty_complex_database_password(self):
        password = "  complex password with symbols :$#@!  "
        environment = {**VALID_PRODUCTION_ENV, "POSTGRES_PASSWORD": password}
        source = """
import os
from django.conf import settings
assert settings.DATABASES["default"]["PASSWORD"] == os.environ["POSTGRES_PASSWORD"]
print("accepted")
"""
        result = self.run_settings(
            "config.settings.production",
            source,
            environment=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "accepted")

    def test_production_rejects_weak_or_example_secret(self):
        for secret in ("too-short", "change-me-" * 10):
            with self.subTest(secret=secret):
                environment = {**VALID_PRODUCTION_ENV, "DJANGO_SECRET_KEY": secret}
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.SECRET_KEY)",
                    environment=environment,
                )
                self.assert_failed_with(result, "DJANGO_SECRET_KEY")
                self.assertNotIn(secret, result.stderr)

    def test_production_rejects_invalid_boolean(self):
        environment = {**VALID_PRODUCTION_ENV, "DJANGO_ENABLE_ADMIN": "sometimes"}
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.ADMIN_ENABLED)",
            environment=environment,
        )

        self.assert_failed_with(result, "must be a boolean")

    def test_production_rejects_invalid_integer(self):
        invalid_values = (
            ("five-four-three-two", "POSTGRES_PORT must be an integer"),
            (" 5432", "POSTGRES_PORT cannot contain surrounding whitespace"),
        )
        for port, message in invalid_values:
            with self.subTest(port=port):
                environment = {**VALID_PRODUCTION_ENV, "POSTGRES_PORT": port}
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.DATABASES)",
                    environment=environment,
                )
                self.assert_failed_with(result, message)

    def test_production_rejects_invalid_database_host(self):
        for host in ("https://database.test", ".database.example.test"):
            with self.subTest(host=host):
                environment = {**VALID_PRODUCTION_ENV, "POSTGRES_HOST": host}
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.DATABASES)",
                    environment=environment,
                )
                self.assert_failed_with(result, "POSTGRES_HOST")

    def test_production_rejects_insecure_database_ssl_mode(self):
        environment = {**VALID_PRODUCTION_ENV, "POSTGRES_SSLMODE": "disable"}
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.DATABASES)",
            environment=environment,
        )

        self.assert_failed_with(result, "POSTGRES_SSLMODE")

    def test_production_rejects_zero_hsts_duration(self):
        environment = {**VALID_PRODUCTION_ENV, "DJANGO_HSTS_SECONDS": "0"}
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.SECURE_HSTS_SECONDS)",
            environment=environment,
        )

        self.assert_failed_with(result, "DJANGO_HSTS_SECONDS must be at least 1")

    def test_production_rejects_empty_or_whitespace_list_items(self):
        invalid_values = (
            ("app.example.test,", "empty list items"),
            ("app.example.test, api.example.test", "surrounding whitespace"),
        )
        for hosts, message in invalid_values:
            with self.subTest(hosts=hosts):
                environment = {**VALID_PRODUCTION_ENV, "DJANGO_ALLOWED_HOSTS": hosts}
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.ALLOWED_HOSTS)",
                    environment=environment,
                )
                self.assert_failed_with(result, message)

    def test_production_rejects_wildcard_or_invalid_hosts(self):
        for host in (
            "*",
            ".example.test",
            "https://app.example.test",
            "bad_host.example.test",
        ):
            with self.subTest(host=host):
                environment = {**VALID_PRODUCTION_ENV, "DJANGO_ALLOWED_HOSTS": host}
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.ALLOWED_HOSTS)",
                    environment=environment,
                )
                self.assert_failed_with(result, "DJANGO_ALLOWED_HOSTS")

    def test_production_rejects_insecure_or_malformed_origins(self):
        invalid_origins = (
            "http://app.example.test",
            "https://app.example.test/path",
            "https://user:password@app.example.test",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                environment = {
                    **VALID_PRODUCTION_ENV,
                    "DJANGO_CSRF_TRUSTED_ORIGINS": origin,
                }
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
                    environment=environment,
                )
                self.assert_failed_with(result, "HTTPS origins")

    def test_origin_validation_error_does_not_leak_credentials(self):
        origin_with_credentials = (
            "https://sensitive-user:sensitive-password@app.example.test"
        )
        environment = {
            **VALID_PRODUCTION_ENV,
            "DJANGO_CSRF_TRUSTED_ORIGINS": origin_with_credentials,
        }
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
            environment=environment,
        )

        self.assert_failed_with(result, "HTTPS origins")
        self.assertNotIn(origin_with_credentials, result.stderr)
        self.assertNotIn("sensitive-password", result.stderr)

    def test_production_rejects_invalid_or_wildcard_origin_hosts(self):
        invalid_origins = (
            "https://bad_host.example.test",
            "https://*.example.test",
            "https://.example.test",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                environment = {
                    **VALID_PRODUCTION_ENV,
                    "DJANGO_CSRF_TRUSTED_ORIGINS": origin,
                }
                result = self.run_settings(
                    "config.settings.production",
                    "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
                    environment=environment,
                )
                self.assert_failed_with(result, "DJANGO_CSRF_TRUSTED_ORIGINS")

    def test_production_is_fail_closed_and_has_no_sqlite_fallback(self):
        source = """
import json
from django.conf import settings
print(json.dumps({
    "debug": settings.DEBUG,
    "admin": settings.ADMIN_ENABLED,
    "engine": settings.DATABASES["default"]["ENGINE"],
    "session_secure": settings.SESSION_COOKIE_SECURE,
    "csrf_secure": settings.CSRF_COOKIE_SECURE,
    "ssl_redirect": settings.SECURE_SSL_REDIRECT,
    "hsts": settings.SECURE_HSTS_SECONDS,
    "proxy_header_configured": settings.SECURE_PROXY_SSL_HEADER is not None,
}))
"""
        result = self.run_settings(
            "config.settings.production",
            source,
            environment=VALID_PRODUCTION_ENV,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertFalse(snapshot["debug"])
        self.assertFalse(snapshot["admin"])
        self.assertEqual(snapshot["engine"], "django.db.backends.postgresql")
        self.assertTrue(snapshot["session_secure"])
        self.assertTrue(snapshot["csrf_secure"])
        self.assertTrue(snapshot["ssl_redirect"])
        self.assertEqual(snapshot["hsts"], 3600)
        self.assertFalse(snapshot["proxy_header_configured"])

    def test_proxy_ssl_header_requires_explicit_opt_in(self):
        environment = {
            **VALID_PRODUCTION_ENV,
            "DJANGO_TRUST_PROXY_SSL_HEADER": "true",
        }
        result = self.run_settings(
            "config.settings.production",
            "from django.conf import settings; print(settings.SECURE_PROXY_SSL_HEADER)",
            environment=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "('HTTP_X_FORWARDED_PROTO', 'https')")

    def test_subprocess_environment_does_not_mutate_parent_process(self):
        name = "DJANGO_PHASE1_SUBPROCESS_SENTINEL"
        original_value = os.environ.get(name)
        result = self.run_settings(
            "config.settings.local",
            f"import os; print(os.environ[{name!r}])",
            environment={name: "child-only"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "child-only")
        self.assertEqual(os.environ.get(name), original_value)


class EntrypointSettingsTests(SettingsProcessMixin, SimpleTestCase):
    def test_manage_py_defaults_to_local_settings(self):
        result = self.run_manage(
            "shell",
            "-c",
            (
                "from django.conf import settings; "
                "print(settings.SETTINGS_MODULE, settings.DEBUG, "
                "settings.DATABASES['default']['ENGINE'])"
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "config.settings.local True django.db.backends.postgresql",
            result.stdout,
        )

    def test_asgi_and_wsgi_default_to_fail_fast_production_settings(self):
        for module in ("config.asgi", "config.wsgi"):
            with self.subTest(module=module):
                result = self.run_settings(
                    "config.settings.local",
                    f"import {module}",
                    remove=("DJANGO_SETTINGS_MODULE",),
                )
                self.assert_failed_with(result, "DJANGO_SECRET_KEY")

    def test_asgi_and_wsgi_respect_explicit_local_settings(self):
        source_template = """
import {module}
from django.conf import settings
print(settings.DEBUG, settings.DATABASES["default"]["ENGINE"])
"""
        for module in ("config.asgi", "config.wsgi"):
            with self.subTest(module=module):
                result = self.run_settings(
                    "config.settings.local",
                    source_template.format(module=module),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.strip(),
                    "True django.db.backends.postgresql",
                )


class AdminAndBootstrapSettingsTests(SettingsProcessMixin, SimpleTestCase):
    route_source = """
import django
django.setup()
from django.urls import Resolver404, resolve
try:
    match = resolve("/admin/")
except Resolver404:
    print("closed")
else:
    print(match.url_name)
"""

    def test_local_admin_route_is_available(self):
        result = self.run_settings("config.settings.local", self.route_source)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "index")

    def test_production_admin_route_is_closed_by_default(self):
        result = self.run_settings(
            "config.settings.production",
            self.route_source,
            environment=VALID_PRODUCTION_ENV,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "closed")

    def test_production_admin_route_requires_explicit_opt_in(self):
        environment = {**VALID_PRODUCTION_ENV, "DJANGO_ENABLE_ADMIN": "true"}
        result = self.run_settings(
            "config.settings.production",
            self.route_source,
            environment=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "index")

    def test_bootstrap_demo_is_rejected_by_production_settings(self):
        source = """
import django
django.setup()
from django.core.management import call_command
from django.core.management.base import CommandError
try:
    call_command("bootstrap_demo")
except CommandError as error:
    print(error)
else:
    raise AssertionError("bootstrap_demo unexpectedly ran")
"""
        result = self.run_settings(
            "config.settings.production",
            source,
            environment=VALID_PRODUCTION_ENV,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("disabled when DEBUG is False", result.stdout)
