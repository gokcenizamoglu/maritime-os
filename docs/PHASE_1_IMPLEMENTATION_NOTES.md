# MaritimeOS — Phase 1 Implementation Notes

## Structure

Nine focused Django apps instead of one monolithic app, matching the four
domain groupings from the brief:

| Group | Apps |
|---|---|
| Core | `tenants`, `customers`, `vessels`, `catalog` (Flag/ServiceType/DocumentType/OrganizationType), `service_requests` |
| Document | `documents`, `checklists` |
| Process | `workflow` |
| Collaboration | `organizations`, `users` |
| Cross-cutting | `activity` (audit log), `config` (base models, urls) |

Every app has, at most, three files that matter: `models.py`, `services.py`,
and (where it's exposed via API) `serializers.py` + `views.py`. Views never
contain business logic — they validate input, call a service function, and
serialize the result. This is what "no fat views" means in practice.

## The five decisions that matter most

**1. ChecklistTemplate vs ChecklistItem are separate tables.**
Templates are configuration (what documents does Owner Change + Panama
require); Items are per-case instances generated from that configuration.
This is what makes "dynamic, admin-editable checklists" actually possible
later — an admin UI just needs to CRUD `ChecklistTemplate` rows, and every
new `ServiceRequest` picks up the change automatically.

**2. `ChecklistItem.is_complete` is a derived cache, not a source of truth.**
The real answer lives in `checklists.services.recompute_checklist_item()`,
which counts qualifying `Document` rows. Nothing else is allowed to write
that field. This is the single invariant most likely to rot if not
enforced at the service layer — a well-meaning bug fix six months from now
that does `item.is_complete = True; item.save()` directly would silently
break the whole system's source of truth.

**3. `Document.document_type` is nullable, and classification is a distinct
service call from upload.** Documents arrive unstructured; they may sit
`unclassified` indefinitely. `classify_document()` is written so that a
future AI classifier can call the exact same function a human does
(`documents.views.DocumentViewSet.classify` today; an async Celery task in
Phase 2) — the checklist/activity side effects don't change based on who
made the call.

**4. `WorkflowStepTemplate.depends_on` is a dependency graph, not a linear
`order` field.** This is required by the real workflow you described:
Registry issued unlocks Radio License, Minimum Safe Manning, and P&I Blue
Card *simultaneously*. `workflow.services.get_eligible_steps()` already
computes "what can start now" from that graph — Phase 1 surfaces it
read-only; Phase 2's automation engine calls the same function to drive
auto-advancement.

**5. `ActivityLog` is generic (verb + entity_type + entity_id + JSON
metadata), not one FK per entity type.** Every service function funnels
through `activity.services.log_activity()`. This is both your Phase 1
"timeline" feature and your Phase 2 compliance audit log — same table,
no migration needed when audit requirements get stricter.

## Multi-tenancy

`TenantScopedModel` (in `config/base_models.py`) is inherited by every
tenant-owned entity. Tenant filtering happens at the view layer
(`get_queryset` methods), never trusted from client input. `catalog`
models (Flag, ServiceType, DocumentType, OrganizationType) are
deliberately **not** tenant-scoped — they're shared maritime-domain
vocabulary, not per-tenant configuration.

## What's intentionally NOT built yet (Phase 2, but designed for)

- **AI document classification**: `Document.classification_confidence` /
  `classification_source` fields exist now so this is an additive feature,
  not a migration.
- **Email ingestion**: `Document.uploaded_by_type` already has a `SYSTEM`
  option and `ActivityLog` already logs uploads generically — an email
  ingestion worker just calls `upload_document()` like any other caller.
- **Workflow automation**: `get_eligible_steps()` exists; only the
  scheduler/trigger that calls it in a loop is missing.
- **Certificate generation & versioning**: `Document.supersedes` already
  models version chains; a generated CSR is just a `Document` whose
  `document_type` is "CSR" and which supersedes the prior version.
- **Event-driven architecture**: every service function already emits one
  clean seam (`log_activity` calls) that a Celery task or message bus
  publisher can hook into without touching business logic.

## What was deliberately left out of Phase 1

- Django Admin registration (trivial to add, omitted here to keep the
  diff focused on domain code)
- Full auth/permission scaffolding beyond tenant isolation (see
  `config/permissions.py`) — role-based permissions (Admin/Ops/Viewer)
  are stubbed on `User.role` but not yet enforced per-endpoint
- Migrations (not generated — run `manage.py makemigrations` once this is
  dropped into a real project with `INSTALLED_APPS` configured)
- Storage backend config (S3 abstraction is a `django-storages` settings
  concern, not a models/services concern, so it's untouched here)

## Production hardening review

A follow-up review pass fixed nine data-integrity, tenant-isolation, and
concurrency bugs in this implementation — see **REVIEW.md** for the full
list, root-cause explanations, and trade-offs. The most serious of these
was a checklist-staleness bug where reclassifying a document didn't
recompute the checklist item it was leaving, so completion state could
silently drift from reality.
