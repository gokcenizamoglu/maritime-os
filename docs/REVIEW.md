# MaritimeOS — Production Hardening Review (Phase 1.1)

This is a review pass over the Phase 1 implementation. No new features
were added. Every change below is a fix to an existing bug or a
tightening of an existing invariant.

## 1. Changes made

| # | Area | File(s) | Fix |
|---|---|---|---|
| 1 | Multi-tenant isolation | `service_requests/serializers.py`, `service_requests/services.py` | `customer`/`vessel` fields now use tenant-scoped querysets, not the DRF default (all tenants). Same check re-asserted in the service layer as a second, independent boundary. |
| 2 | Document upload pipeline | `documents/views.py`, `documents/serializers.py` | `DocumentViewSet.create()` overridden to route through `upload_document()` instead of the default `ModelViewSet` create flow, which bypassed activity logging and checklist matching entirely. |
| 3 | Reclassification staleness | `documents/services.py` | `classify_document()` now recomputes the **previous** checklist item too, not just the newly matched one. Previously a reclassified document left its old checklist item stuck at `is_complete=True`. |
| 4 | Reference code race condition | `service_requests/models.py`, `service_requests/services.py` | Replaced `count() + 1` with a `select_for_update()`-locked `ServiceRequestSequence` row per (tenant, year). |
| 5 | Workflow step duplication | `workflow/services.py` | Templates are now de-duplicated by `code` (preferring flag-specific over global) before instantiation, preventing two `WorkflowStepInstance`s for what's conceptually one step. |
| 6 | Vessel IMO uniqueness | `vessels/models.py` | Changed from a global `unique=True` to a `UniqueConstraint(tenant, imo_number)` — justification inline in the model docstring. |
| 7 | Checklist correctness | `checklists/serializers.py` | `mapped_document_count` now excludes superseded documents, matching the logic already used by `recompute_checklist_item()`. |
| 8 | Permissions | `config/permissions.py` (new), applied in 3 viewsets | Added `IsTenantMember` + `IsSameTenantObject` as an explicit, testable object-level backstop behind queryset filtering. |
| 9 | Activity logging | `checklists/services.py` | `recompute_checklist_item()` now logs `checklist_item.completion_changed` — previously checklist state changes were invisible in the audit trail even though the documents that caused them were logged. |
| 10 | Classification model | `documents/models.py` | Removed the unused `classification_source` enum; kept `document_type` (confirmed) + added `predicted_document_type` (Phase 2 AI suggestion) + `classification_confidence`. |
| 11 | Multi-document checklist items | *(no change needed)* | Already correctly supported — `Document.checklist_item` is many-to-one, `ChecklistItem.required_count` already gates completion on a count, not a single document. Confirmed, not touched. |

## 2. Explanation of each fix

**#1 — Multi-tenant isolation.** The original `ServiceRequestCreateSerializer`
declared `customer`/`vessel` as plain model fields, which DRF resolves to
`PrimaryKeyRelatedField(queryset=Customer.objects.all())` — i.e. any
tenant's ID was accepted as long as it existed anywhere in the database.
The existing `vessel.customer == customer` cross-check caught some
mismatches by luck, not by design — a request using *another* tenant's
customer_id together with *that same* tenant's matching vessel_id would
have passed. Fixed at two independent layers: the serializer now scopes
both querysets to `request.user.tenant`, and `create_service_request()`
in the service layer re-asserts tenant ownership regardless of caller.

**#2 — Document upload pipeline.** `DocumentViewSet` extended
`ModelViewSet` with no `create()` override, so DRF's default flow ran:
validate `DocumentSerializer` → `serializer.save()` → raw
`Document.objects.create()`. That path never touched
`documents.services.upload_document()`, so internally-uploaded documents
got no `ActivityLog` entry and no checklist wiring — while the public
customer-portal upload (which already called the service function
directly) worked correctly. Fixed by overriding `create()` to use a
minimal input-only serializer and call the service function explicitly.

**#3 — Reclassification staleness.** This was the most serious
correctness bug. `is_complete` is supposed to be *fully derived* from
document mappings, but the previous `classify_document()` only ever
looked forward: when a document moved to a new `DocumentType`, it found
and recomputed the item for the *new* type, and never revisited the
item for the *old* type the document had just vacated. A corrected
misclassification could leave a checklist showing 100% complete for a
requirement that, in reality, no longer had a qualifying document
attached. Fixed by capturing `document.checklist_item` before
reassignment and unconditionally recomputing it alongside the new one.

**#4 — Reference code race.** `count() + 1` inside a transaction is not
protected by the transaction itself against a concurrent transaction
also reading the same count before either commits — Postgres's default
`READ COMMITTED` isolation does not serialize this. Two simultaneous
`ServiceRequest` creations for the same tenant could generate the same
`reference_code`, and the DB's `unique=True` constraint would then
reject the second insert as a 500, not a clean validation error. Fixed
with a locked counter row: `select_for_update()` blocks the second
transaction until the first commits, guaranteeing strictly increasing,
non-colliding numbers, scoped per tenant so unrelated tenants never
contend for the same lock.

**#5 — Workflow step duplication.** `WorkflowStepTemplate`'s uniqueness
is `(service_type, flag, code)` — a deliberate design allowing a
flag-specific override of a generically-named step. But the generation
query fetched every template matching `flag=X OR flag IS NULL` and
instantiated *all* of them, so a global "lawyer_review" template and a
Panama-specific "lawyer_review" template both being present produced
two separate `WorkflowStepInstance`s for the same conceptual step. Fixed
by reducing candidates to one template per `code` before instantiation,
preferring the more specific (flag-matched) template when both exist.

**#6 — Vessel IMO uniqueness.** Real-world IMO numbers are globally
unique to the ship, which made a blanket global `unique=True` look
correct at first glance. But this is multi-tenant B2B SaaS: the same
physical vessel can be a legitimate client of two unrelated
consultancies (switching agents, or using separate agents per flag
jurisdiction). A global constraint would mean Tenant A onboarding a
vessel permanently blocks Tenant B from ever registering that same ship
— an availability bug disguised as a data-integrity rule. Scoped the
uniqueness to `(tenant, imo_number)` instead.

**#7 — mapped_document_count.** The serializer's count didn't apply the
same `superseded_by_set__isnull=True` exclusion that
`recompute_checklist_item()` already used, so the UI could show a
mapped-document count inconsistent with the authoritative `is_complete`
flag next to it (e.g. showing "2 mapped" including a corrected, replaced
version, on an item whose real qualifying count is 1). Now both use
identical filtering.

**#8 — Permissions.** Tenant isolation existed only as an implicit
side-effect of `get_queryset()` filtering. That's necessary, but a
single future `@action` or custom `get_object()` override anywhere in
the codebase could silently reintroduce cross-tenant access with no
test catching it, because nothing *enforces* the check independent of
the query. `IsSameTenantObject` makes that check an explicit,
independently unit-testable permission class applied at the DRF
framework level, on top of (not instead of) queryset filtering.

**#9 — Checklist activity logging.** Document-level events
(`document.uploaded`, `document.classified`) were logged, but the
checklist-level *consequence* of those events — an item flipping
complete/incomplete — was not. Support staff investigating "why does
this case say Ready" had no record of which specific completion changes
occurred. Added a log call inside `recompute_checklist_item()`, gated on
an actual state change (not logged on every recompute — only when
`is_complete` actually flips) to avoid log noise.

**#10 — Classification model.** The original `classification_source`
enum (manual/ai) had no consumer anywhere in the code — an abstraction
added preemptively. Removed it in favor of the more useful
`predicted_document_type` field, which lets a future AI classifier write
its *guess* without touching the confirmed `document_type` field at all,
and makes "was this AI-suggested" simply "does `predicted_document_type`
differ from `document_type`" — derivable, not stored redundantly.

## 3. Trade-offs made

- **`select_for_update()` on the sequence row serializes ServiceRequest
  creation per (tenant, year).** For a single consultancy this is a
  non-issue (nobody is creating hundreds of cases per second), but if a
  future large enterprise tenant needs very high write concurrency for
  case creation specifically, a Postgres native sequence
  (`django.db.models.functions.Now` + `nextval()`) would remove even
  this narrow lock at the cost of losing the clean per-tenant-per-year
  numbering format. Not changed now — Phase 1 volumes don't justify it.
- **`IsSameTenantObject`'s fallback logic (`tenant_id` then
  `service_request.tenant_id`) is a convention, not enforced by an
  interface/protocol.** A model that stores its tenant relationship
  under some third name would silently fail the permission's `hasattr`
  checks and return `False` (fail-closed, which is the safe default) —
  but it's worth adding a short comment/test whenever a new model type
  is wired into one of these viewsets.
- **Left `ServiceRequestOrganization`'s tenant consistency unchecked** —
  it wasn't reachable through any exposed endpoint in Phase 1, so it was
  out of scope for this pass. Flagging it: when it is exposed, apply the
  same tenant-membership assertion pattern used in
  `create_service_request()`.

## 4. Suggestions for next phase

- Add an automated test suite covering exactly the bugs fixed here
  (cross-tenant customer/vessel rejection, reclassification staleness,
  duplicate workflow steps, concurrent reference-code generation) so
  regressions are caught before review, not during it.
- Enforce `User.role` (Admin/Ops/Viewer) at the endpoint level — it
  exists on the model but nothing currently checks it.
- Consider Postgres row-level security as a second, DB-enforced layer of
  tenant isolation beneath the application-level checks added here.
