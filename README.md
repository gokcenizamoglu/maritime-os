# MaritimeOS

A domain-heavy, event-driven, multi-tenant SaaS platform for maritime
consultancies — managing flag registration, crew, survey, and project
management workflows where processes are parallel (not linear), heavily
document-driven, and vary by flag state.

## Monorepo structure

```
MaritimeOS/
├── backend/     Django + Django REST Framework API (see backend/README.md history in docs/)
├── frontend/    Next.js (App Router, TypeScript, Tailwind CSS) UI
├── docs/        Architecture and project documentation
├── .gitignore
└── README.md    This file
```

One repository for backend and frontend — no separate repos.

## Backend

The backend lives entirely under [`backend/`](backend/): Django project
settings + all domain apps (`tenants`, `service_requests`, `documents`,
`checklists`, `workflow`, `activity`, `rules`, `events`, etc.), each
following a strict service-layer / event-driven architecture. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/RULES_ENGINE.md`](docs/RULES_ENGINE.md), and
[`docs/PHASE_1_IMPLEMENTATION_NOTES.md`](docs/PHASE_1_IMPLEMENTATION_NOTES.md)
for the design history and rationale.
Tenant catalog and versioned operation-template behavior is documented in
[`docs/TENANT_CATALOG_AND_OPERATION_TEMPLATES.md`](docs/TENANT_CATALOG_AND_OPERATION_TEMPLATES.md).

### Dependencies

Split by environment under [`backend/requirements/`](backend/requirements/):

- `base.txt` — pinned runtime dependencies, including PostgreSQL support
- `dev.txt` — local development dependency entrypoint
- `test.txt` — local and CI test dependency entrypoint
- `production.txt` — production dependency entrypoint

Install with `pip install -r backend/requirements/dev.txt` for local
development.

### Running backend tests

From the `backend/` directory:

```bash
cd backend
pip install -r requirements/test.txt
python manage.py test --settings=config.settings.test
```

### Running the backend locally

```bash
docker compose up -d db
cd backend
python manage.py runserver
```

Local development uses PostgreSQL and `config.settings.local`. Environment
selection, production fail-fast configuration, and CI are documented in
[`docs/PRODUCTION_CONFIGURATION_AND_CI.md`](docs/PRODUCTION_CONFIGURATION_AND_CI.md).

## Frontend

Next.js (App Router, TypeScript, Tailwind CSS) app under
[`frontend/`](frontend/). Authentication is implemented through the Django
session API and the Next.js server-side relay; the Operations list/detail
flow is connected to the backend. The tenant catalog and operation-template
management surface is currently backend/API-first; see
[`frontend/README.md`](frontend/README.md) for the current UI boundary.

### Install

```bash
cd frontend
npm ci
```

### Environment variable

Copy `frontend/.env.example` to `frontend/.env.local` and set:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

This is the only environment variable currently required — it points
the frontend at the backend's API base URL (read in
`frontend/src/lib/api/config.ts`, never hardcoded in application code).

### Run

```bash
cd frontend
npm run dev
```

Opens at [http://localhost:3000](http://localhost:3000).

## Documentation

Architecture decisions, the rule engine design, and phase-by-phase
implementation notes live in [`docs/`](docs/).
