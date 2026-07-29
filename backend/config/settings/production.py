from django.core.exceptions import ImproperlyConfigured

from config.environment import (
    env_bool,
    env_csv,
    env_int,
    env_value,
    postgres_database,
    validate_host,
    validate_https_origin,
)
from config.settings.base import *  # noqa: F403


DEBUG = False

SECRET_KEY = env_value("DJANGO_SECRET_KEY", required=True)
if (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 20
    or any(
        marker in SECRET_KEY.lower()
        for marker in ("change-me", "changeme", "example", "insecure", "local-only")
    )
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be at least 50 characters, have sufficient variety, "
        "and must not be an example or development value."
    )

ALLOWED_HOSTS = env_csv(
    "DJANGO_ALLOWED_HOSTS",
    required=True,
    validate=validate_host,
)
CSRF_TRUSTED_ORIGINS = env_csv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    required=True,
    validate=validate_https_origin,
)

DATABASES = {
    "default": postgres_database(require_all=True, require_secure_ssl=True),
}

ADMIN_ENABLED = env_bool("DJANGO_ENABLE_ADMIN", default=False)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = True

SECURE_HSTS_SECONDS = env_int(
    "DJANGO_HSTS_SECONDS",
    required=True,
    minimum=1,
    maximum=63072000,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", default=False)

if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
