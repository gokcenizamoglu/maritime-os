"""
Minimal Django project settings — wraps the existing domain apps so the
codebase can actually run (`migrate`, `runserver`, `shell`, tests) on
SQLite. This file adds NO domain behavior: it is pure Django/DRF wiring
(INSTALLED_APPS, DATABASES, auth model, URL root) so that code already
written in each app's models.py/services.py/views.py becomes runnable.

Lives at the Django project root, i.e. `backend/` (next to manage.py),
not inside the existing `config` app, so it doesn't collide with
`config`'s own contents (`base_models.py`, `permissions.py`, `urls.py`)
— those are domain files, this is project wiring. `ROOT_URLCONF` below
points at the EXISTING `config/urls.py` unchanged. `backend/` is one
part of the MaritimeOS monorepo (siblings: `frontend/`, `docs/`) — this
file only configures the Django project, nothing repo-wide.

Dev-only. Not for production (see the brief this was scoped to): SECRET_KEY
is a placeholder, DEBUG is on, ALLOWED_HOSTS is open, SQLite is the engine.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",

    # events must use the dotted AppConfig path so EventsConfig.ready()
    # fires and registers every domain's listeners exactly once — see
    # events/apps.py and events/bootstrap.py.
    "events.apps.EventsConfig",

    # Existing domain apps, unmodified.
    "tenants",
    "users",
    "customers",
    "vessels",
    "catalog",
    "organizations",
    "service_requests",
    "documents",
    "checklists",
    "emails",
    "workflow",
    "activity",
    "rules",
    "config",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

AUTH_USER_MODEL = "users.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
