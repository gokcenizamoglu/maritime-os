from dotenv import load_dotenv

from config.environment import env_bool, env_csv, postgres_database, validate_host
from config.settings.base import *  # noqa: F403


if env_bool("DJANGO_LOAD_DOTENV", default=True):
    load_dotenv(REPOSITORY_ROOT / ".env", override=False)  # noqa: F405

DEBUG = True
SECRET_KEY = "local-only-insecure-key-never-use-in-production"
ALLOWED_HOSTS = env_csv(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]"],
    validate=validate_host,
)
CSRF_TRUSTED_ORIGINS = env_csv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
ADMIN_ENABLED = env_bool("DJANGO_ENABLE_ADMIN", default=True)

DATABASES = {
    "default": postgres_database(
        defaults={
            "POSTGRES_DB": "maritimeos",
            "POSTGRES_USER": "maritimeos",
            "POSTGRES_PASSWORD": "maritimeos-local-only",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": "5432",
            "POSTGRES_SSLMODE": "disable",
        }
    )
}
