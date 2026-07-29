from config.environment import env_bool, postgres_database
from config.settings.base import *  # noqa: F403


DEBUG = False
SECRET_KEY = "test-only-insecure-key-never-use-outside-tests"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
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

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
