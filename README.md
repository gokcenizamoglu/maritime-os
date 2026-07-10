# MaritimeOS

A domain-heavy, event-driven, multi-tenant SaaS platform for maritime
consultancies — managing flag registration, crew, survey, and project
management workflows where processes are parallel (not linear), heavily
document-driven, and vary by flag state.

## Monorepo structure

```
MaritimeOS/
├── backend/     Django + Django REST Framework API (see backend/README.md history in docs/)
├── frontend/    Placeholder — not initialized yet
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

### Dependencies

Split by environment under [`backend/requirements/`](backend/requirements/):

- `base.txt` — runtime dependencies (Django, djangorestframework)
- `dev.txt` — `-r base.txt` + development-only packages (currently none needed — see the file for why)
- `production.txt` — `-r base.txt` + production-only packages (currently none — see the file; server/DB/secrets choices aren't made yet)

Install with `pip install -r backend/requirements/dev.txt` for local
development.

### Running backend tests

From the `backend/` directory:

```bash
cd backend
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py test
```

### Running the backend locally

```bash
cd backend
python manage.py runserver
```

Dev-only setup: SQLite, `DEBUG=True`. Not configured for production.

## Frontend

Not initialized yet. `frontend/` currently exists as an empty
placeholder directory reserved for the future Next.js application.

## Documentation

Architecture decisions, the rule engine design, and phase-by-phase
implementation notes live in [`docs/`](docs/).
