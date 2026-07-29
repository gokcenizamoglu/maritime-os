# Production Configuration, PostgreSQL, and CI

Phase 1 separates configuration and proves the application against PostgreSQL.
It does not deploy the application or provide a production platform.

## Supported toolchain

- Python 3.13
- Node.js 20
- npm with `frontend/package-lock.json`
- Docker with Compose support
- PostgreSQL 17 for local development and CI

The domain models do not use GeoDjango fields or GIS queries, so PostGIS is not
required. If GIS is introduced later, both local and CI images must be changed
together and the full migration/test proof repeated.

## Local setup

Create an untracked local environment file from the safe example:

```bash
cp .env.example .env
```

The checked-in values are local-only. Do not reuse them in production. Start
PostgreSQL and wait until Compose reports the service as healthy:

```bash
docker compose up -d db
docker compose ps
```

Install and start the backend:

```bash
cd backend
python -m pip install -r requirements/dev.txt
python manage.py migrate
python manage.py bootstrap_demo
python manage.py runserver
```

`manage.py` selects `config.settings.local` only when
`DJANGO_SETTINGS_MODULE` is not already set. Local settings load the repository
root `.env` without overriding variables already supplied by the process.
They use PostgreSQL, enable `DEBUG`, and expose `/admin/` on localhost.
Because local settings must already be selected before `.env` can be loaded,
`DJANGO_SETTINGS_MODULE` and `DJANGO_LOAD_DOTENV` are process-level controls
and are intentionally not values in `.env.example`.

Start the frontend in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend has its own ignored `frontend/.env.local`; see
`frontend/.env.example`.

The named volume `maritimeos_postgres_data` preserves local data across normal
container restarts. A command such as `docker compose down -v` deletes that
data and is deliberately not part of the setup flow.

## Settings selection

| Environment | Settings module | Database | Admin route |
| --- | --- | --- | --- |
| Local | `config.settings.local` | PostgreSQL | Enabled by default |
| Test/CI | `config.settings.test` | PostgreSQL | Enabled for admin tests |
| Production | `config.settings.production` | PostgreSQL | Disabled by default |

Run tests locally against the same database contract as CI:

```bash
cd backend
python manage.py test --settings=config.settings.test
```

Test settings use Django's fast MD5 password hasher and in-memory email backend.
They do not disable migrations, constraints, transactions, or tenant checks.

ASGI and WSGI entrypoints default to production settings. Production
environments should still set `DJANGO_SETTINGS_MODULE` explicitly so the
selected configuration is visible in deployment configuration.

## Environment contract

Production requires all of these values and refuses to start when one is
missing or malformed:

- `DJANGO_SECRET_KEY`: at least 50 characters with sufficient variety; no
  example or local-development marker.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hostnames without schemes, paths,
  wildcard `*` or leading-dot subdomain wildcards, empty items, duplicates,
  or surrounding whitespace.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: comma-separated HTTPS origins without paths,
  credentials, query strings, fragments, wildcard hosts, empty items, or
  whitespace.
- `DJANGO_HSTS_SECONDS`: integer from 1 through 63072000.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and
  `POSTGRES_PORT`.
- `POSTGRES_SSLMODE`: `require`, `verify-ca`, or `verify-full`.

Optional values:

- `DJANGO_ENABLE_ADMIN`: strict boolean; defaults to `false` in production.
- `DJANGO_HSTS_INCLUDE_SUBDOMAINS` and `DJANGO_HSTS_PRELOAD`: strict booleans;
  both default to `false` for staged HSTS adoption.
- `DJANGO_TRUST_PROXY_SSL_HEADER`: strict boolean; defaults to `false`.
- `POSTGRES_CONN_MAX_AGE`: integer from 0 through 3600.

Keep `POSTGRES_CONN_MAX_AGE=0` when serving through ASGI, as Django does not
recommend persistent database connections for ASGI. A positive value should
only be selected for a reviewed WSGI deployment and database connection budget.

Boolean values accept only `1/0`, `true/false`, `yes/no`, or `on/off`
(case-insensitive). Production never loads `.env`, never falls back to SQLite,
and never falls back to the local secret or database credentials.

`DJANGO_TRUST_PROXY_SSL_HEADER=true` is valid only when a trusted reverse proxy
removes client-supplied forwarding headers and sets `X-Forwarded-Proto`
itself. Leave it disabled otherwise.

## Production security boundary

Production forces `DEBUG=False`, secure session and CSRF cookies, HTTPS
redirect, HSTS, content-type sniffing protection, same-origin referrer policy,
and clickjacking protection. Start HSTS with an operationally reviewed short
duration; enable subdomains and preload only after every affected host is
permanently HTTPS.

The production admin route is absent unless `DJANGO_ENABLE_ADMIN=true`.
Changing or hiding its URL is not treated as a security control. Even when
enabled, do not expose admin to the internet until HTTPS, MFA, login rate
limiting or lockout, secure cookie/session controls, and preferably VPN,
IP allowlisting, or an identity-aware proxy are operating and reviewed.
Phase 1 does not implement MFA or rate limiting.

`bootstrap_demo` is blocked whenever `DEBUG=False`, including production.

## Continuous integration

`.github/workflows/ci.yml` runs for pull requests and pushes to `main`.
Backend and frontend are independent parallel jobs:

- Backend starts a health-checked PostgreSQL 17 service, installs pinned test
  dependencies, runs the Django check, checks migration drift, migrates a clean
  database, verifies migration state, and runs the full test suite.
- Frontend uses `npm ci`, then runs lint, TypeScript checking, and a production
  build.

The workflow has read-only repository permission. It has no deployment, SSH,
registry push, server access, or production secret.

## Dependency security note

The Phase 1 review upgraded `next` and `eslint-config-next` from 16.2.10 to
16.2.12 to remove the directly patched Next.js advisories. At review time,
`npm audit --omit=dev` still reports three high-severity findings through
Next.js's supported `postcss@8.4.31` and `sharp@0.34.5` dependency chain.
No `overrides` or forced downgrade is used to hide them because npm does not
offer a compatible supported resolution. Re-run the production audit and
upgrade to a supported patched Next.js dependency chain before deployment.
