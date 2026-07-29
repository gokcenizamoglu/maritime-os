import ipaddress
import os
import re
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


T = TypeVar("T")
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_DOMAIN_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def env_value(name: str, *, default: T | None = None, required: bool = False) -> str | T:
    value = os.environ.get(name)
    if value is None:
        if required:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}.")
        return default
    if value == "":
        raise ImproperlyConfigured(f"Environment variable {name} cannot be empty.")
    return value


def env_bool(name: str, *, default: bool | None = None, required: bool = False) -> bool:
    value = env_value(name, default=default, required=required)
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ImproperlyConfigured(f"Environment variable {name} must be a boolean.")

    normalized = value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    accepted = ", ".join(sorted(_TRUE_VALUES | _FALSE_VALUES))
    raise ImproperlyConfigured(
        f"Environment variable {name} must be a boolean ({accepted}); got {value!r}."
    )


def env_int(
    name: str,
    *,
    default: int | None = None,
    required: bool = False,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = env_value(name, default=default, required=required)
    if isinstance(value, int):
        parsed = value
    else:
        if not isinstance(value, str):
            raise ImproperlyConfigured(f"Environment variable {name} must be an integer.")
        if value != value.strip():
            raise ImproperlyConfigured(
                f"Environment variable {name} cannot contain surrounding whitespace."
            )
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ImproperlyConfigured(
                f"Environment variable {name} must be an integer; got {value!r}."
            ) from exc

    if minimum is not None and parsed < minimum:
        raise ImproperlyConfigured(
            f"Environment variable {name} must be at least {minimum}; got {parsed}."
        )
    if maximum is not None and parsed > maximum:
        raise ImproperlyConfigured(
            f"Environment variable {name} must be at most {maximum}; got {parsed}."
        )
    return parsed


def env_csv(
    name: str,
    *,
    default: list[str] | tuple[str, ...] | None = None,
    required: bool = False,
    validate: Callable[[str, str], T] | None = None,
) -> list[str] | list[T]:
    value = env_value(name, default=default, required=required)
    if isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, str):
        items = value.split(",")
    else:
        raise ImproperlyConfigured(f"Environment variable {name} must be a CSV list.")

    if not items:
        raise ImproperlyConfigured(f"Environment variable {name} cannot be an empty list.")
    if any(not item for item in items):
        raise ImproperlyConfigured(
            f"Environment variable {name} cannot contain empty list items."
        )
    if any(item != item.strip() for item in items):
        raise ImproperlyConfigured(
            f"Environment variable {name} cannot contain surrounding whitespace."
        )
    if len(items) != len(set(items)):
        raise ImproperlyConfigured(
            f"Environment variable {name} cannot contain duplicate values."
        )
    if validate is None:
        return items
    return [validate(item, name) for item in items]


def validate_host(host: str, variable_name: str) -> str:
    if host == "*":
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} cannot contain wildcard host '*'."
        )
    if any(character.isspace() for character in host):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid host: {host!r}."
        )
    if any(character in host for character in ("://", "/", "\\", "?", "#", "@")):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid host: {host!r}."
        )

    if host.startswith("."):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid host: {host!r}."
        )

    candidate = host
    if candidate.startswith("[") and candidate.endswith("]"):
        try:
            ipaddress.IPv6Address(candidate[1:-1])
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"Environment variable {variable_name} contains an invalid host: {host!r}."
            ) from exc
        return host

    try:
        ipaddress.ip_address(candidate)
        return host
    except ValueError:
        pass

    labels = candidate.split(".")
    if not candidate or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid host: {host!r}."
        )
    return host


def validate_https_origin(origin: str, variable_name: str) -> str:
    if any(character.isspace() for character in origin):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid origin."
        )

    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid origin."
        ) from exc

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or origin != f"{parsed.scheme}://{parsed.netloc}"
    ):
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} must contain HTTPS origins without "
            "paths, credentials, queries, or fragments."
        )
    if port is not None and not 1 <= port <= 65535:
        raise ImproperlyConfigured(
            f"Environment variable {variable_name} contains an invalid origin port."
        )
    validate_host(parsed.hostname, variable_name)
    return origin


def postgres_database(
    *,
    defaults: dict[str, str] | None = None,
    require_all: bool = False,
    require_secure_ssl: bool = False,
) -> dict:
    defaults = defaults or {}
    required_names = {
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    }

    def database_value(name: str) -> str:
        return env_value(
            name,
            default=defaults.get(name),
            required=require_all and name in required_names,
        )

    sslmode = env_value(
        "POSTGRES_SSLMODE",
        default=defaults.get("POSTGRES_SSLMODE"),
        required=require_secure_ssl,
    )
    if sslmode is not None:
        accepted_ssl_modes = (
            {"require", "verify-ca", "verify-full"}
            if require_secure_ssl
            else {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        )
        if sslmode not in accepted_ssl_modes:
            raise ImproperlyConfigured(
                "Environment variable POSTGRES_SSLMODE must be one of "
                f"{', '.join(sorted(accepted_ssl_modes))}; got {sslmode!r}."
            )

    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_value("POSTGRES_DB"),
        "USER": database_value("POSTGRES_USER"),
        "PASSWORD": database_value("POSTGRES_PASSWORD"),
        "HOST": validate_host(database_value("POSTGRES_HOST"), "POSTGRES_HOST"),
        "PORT": env_int(
            "POSTGRES_PORT",
            default=int(defaults["POSTGRES_PORT"]) if "POSTGRES_PORT" in defaults else None,
            required=require_all,
            minimum=1,
            maximum=65535,
        ),
        "CONN_MAX_AGE": env_int(
            "POSTGRES_CONN_MAX_AGE",
            default=0,
            minimum=0,
            maximum=3600,
        ),
    }
    if sslmode is not None:
        config["OPTIONS"] = {"sslmode": sslmode}
    return config
