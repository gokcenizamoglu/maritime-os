# MaritimeOS — Architectural Elevation Pass (Phase 1.2)

No new user-facing features. This pass restructures HOW the existing
domains talk to each other, so the next features (AI classification,
email ingestion, workflow automation, external integrations) are
additive, not rewrites.

## 1. Architectural improvements applied

| # | Improvement | What changed |
|---|---|---|
| 1 | **Domain event system** (new `events` app) | `documents.services` no longer imports `checklists.services` or `activity.services` directly. It calls `events.dispatcher.emit(...)`; consuming domains subscribe via `@on(...)` in their own `listeners.py`. |
| 2 | **ServiceRequest state as a real domain concept** | `service_requests/state_machine.py` now has GUARDS in addition to the transition graph — e.g. you cannot move to `Ready` with an incomplete checklist, or to `Completed` with open workflow steps, regardless of what the graph alone would allow. |
| 3 | **Workflow orchestration layer** | `WorkflowStepInstance.Status` gained `BLOCKED`/`ACTIVE` (replacing the passive `IN_PROGRESS`); `workflow.services.sync_step_statuses()` actively moves steps between `PENDING`↔`BLOCKED` based on dependency completion, instead of `get_eligible_steps()` being a read-only query nothing acted on. Added `workflow/state_machine.py` for step-level transition validation. |
| 4 | **Activity Log → Timeline System** | `activity.services.log_activity()` now accepts a human-readable `summary`; `build_timeline_entry()` structures a raw log row into `{verb, summary, actor, timestamp, context, metadata}`; `activity/listeners.py` centralizes summary-building for every event type in one place instead of five. New read endpoint: `GET /api/service-requests/{id}/timeline/`. |
| 5 | **Document intelligence separation** | `Document.document_type` (confirmed) vs `Document.predicted_document_type` (Phase 2 AI suggestion) are now distinct fields — removed the unused `classification_source` enum abstraction that had no consumer. |
| 6 | **Email ingestion interface** (new `emails` app) | `EmailMessage` model + `ingest_email()` / `extract_documents_from_email()` service functions define WHERE email plugs in and WHAT it calls, without implementing a mail client. `Document.source_email` traces an extracted document back to its email. |
| 7 | **Organization role consistency** | New `organizations/services.py::attach_organization_to_service_request()` enforces tenant match and role/organization-type consistency (e.g. only a `law_firm`-typed Organization can hold the `HANDLING_LAWYER` role) — previously nothing validated this. |
| 8 | **Service layer hardening** | Every remaining direct cross-domain service import was audited and removed in favor of events (verified via `grep` — see below). Views remain thin; no logic moved into serializers or views during this pass. |
| 9 | **Explicit domain boundaries** | Document domain (`documents`, `checklists`, `emails`) / Process domain (`service_requests`, `workflow`) / Collaboration domain (`organizations`, `users`) / Cross-cutting (`activity`, `events`, `config`) — now enforced structurally: cross-domain communication happens ONLY through `events`, `catalog` (shared vocabulary), or explicit composition roots (`create_service_request` calling checklist/workflow generation directly, which is a deliberate exception — see its docstring). |

## 2. Updated code

New files: `events/dispatcher.py`, `events/types.py`, `events/bootstrap.py`,
`emails/models.py`, `emails/services.py`, `workflow/state_machine.py`,
`workflow/listeners.py` *(not created — see note in `bootstrap.py`: no
cross-domain workflow listener exists yet)*, `workflow/serializers.py`,
`workflow/views.py`, `activity/listeners.py`, `activity/views.py`,
`checklists/listeners.py`, `organizations/services.py`.

Rewritten: `documents/services.py` (emits events instead of direct
calls), `checklists/services.py` (emits `CHECKLIST_ITEM_COMPLETION_CHANGED`
instead of logging directly), `service_requests/services.py` /
`state_machine.py` (guards added, emits events), `workflow/services.py`
(orchestration + events), `activity/services.py` (`summary` param +
`build_timeline_entry`), `documents/models.py` (`predicted_document_type`,
`source_email`, removed `classification_source`), `config/urls.py`
(workflow + timeline routes registered).

## 3. Explanation of each improvement

**Why events, not just "call the function directly but more carefully"?**
The hardening pass already fixed the reclassification bug by making
`classify_document()` remember to call `recompute_checklist_item()` on
both the old and new item. That fix is correct, but it means every
FUTURE consequence of a document event (notify the customer, trigger an
AI re-check, kick off an email draft) has to be ANOTHER line added
inside `classify_document()` — the document domain keeps accumulating
knowledge of everyone downstream. Events flip the dependency direction:
`documents/services.py` now imports nothing from `checklists` or
`activity` at all (verified — see the grep check in the review). It
announces facts; other domains decide what those facts mean to them.

**Why guards on the state machine, not just the transition graph?**
"Model state as a domain concept, not a free string" was the explicit
ask. A transition graph alone still lets you free-string your way into
nonsense the graph doesn't forbid (moving to Ready with 0% checklist
complete was legal under the OLD graph-only check, because the graph
only knows about the shape of the diagram, not the specific case's
data). Guards close that: they're domain rules with access to the
actual ServiceRequest, not just its status string.

**Why BLOCKED as a real status instead of computing eligibility on
read?** A step sitting in the database with no record of WHY it can't
start yet is invisible to any future UI, report, or automation trigger
— "what does the case look like right now" required re-running a
dependency query every time. Making `BLOCKED` a persisted status means
the orchestration state IS the data, queryable directly
(`WorkflowStepInstance.objects.filter(status='blocked')`), which is
exactly what a future automation engine or dashboard needs.

**Why a separate `emails` app now, with no working ingestion?**
Because the two structural questions — where does an email attach to a
case, and what does the ingestion pipeline call once it's parsed a
message — are exactly the questions that are expensive to retrofit if
skipped. Building the actual IMAP/Graph API client and subject-parsing
heuristics is real, separate work; the DATA MODEL and SERVICE INTERFACE
it will use are cheap to lock in now and expensive to bolt on later
(they'd otherwise require a migration touching `Document`, which is
already a hot table).

## 4. How this prepares Phase 2

- **AI document classification**: writes to `predicted_document_type` /
  `classification_confidence`, then calls the SAME `classify_document()`
  to confirm — zero changes needed to checklist or activity logic,
  because those are event-driven, not called directly by
  `classify_document()`.
- **Email ingestion**: an adapter (IMAP/Graph API client + subject/sender
  matching) calls `emails.services.ingest_email()` then
  `extract_documents_from_email()` — both already route through the
  existing, event-instrumented `upload_document()`.
- **Workflow automation**: a scheduler/webhook calling
  `workflow.services.sync_step_statuses()` on a timer, or calling
  `update_step_status()` when an external organization's response
  arrives, is the entire "automation engine" — the state machine and
  dependency logic it needs already exist.
- **External system integrations** (flag authority portals, P&I club
  APIs): `organizations.services.attach_organization_to_service_request()`
  plus `WorkflowStepInstance.assigned_organization` are the seam — a
  future `integrations` app builds adapters that call these, rather than
  reaching into `ServiceRequest` or `Document` internals directly.
- **Async processing** (explicitly NOT built this pass): `events.emit()`
  is the single choke point where synchronous dispatch becomes
  `.delay()` — every existing call site (`emit(DOCUMENT_CLASSIFIED, ...)`
  etc.) keeps working unchanged.
