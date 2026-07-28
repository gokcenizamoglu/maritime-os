# MaritimeOS — Frontend Information Architecture

Status: **Phase 1 decisions locked below are final for this slice.** This
document supersedes the exploratory IA proposal wherever they conflict — the
scope here is deliberately narrower, based on what the backend actually
supports today (verified by reading `backend/config/urls.py` and every
registered viewset, not assumed).

---

## 1. Core principle — DECIDED

**Operations is the center of the product.** There is exactly one shared
`ServiceRequest` list and one shared `ServiceRequest` detail experience in
the frontend, matching the backend: there is one aggregate-root model
(`ServiceRequest`), not separate `SurveyRequest`/`CrewRequest`/`FlagRequest`
models. The frontend must not invent parallel screens the backend has no
concept of. Future module-specific behavior (Crew, Survey, Flag Registration,
Project Management) will **extend** the shared `ServiceRequest` detail page
(additional tabs/sections, entitlement-gated) — it will never duplicate it
into a separate screen.

## 2. Phase 1 sidebar — DECIDED, backend-verified scope

Only navigation backed by a real, existing backend endpoint is visible:

| Item | Route | Backend support |
|---|---|---|
| Dashboard | `/dashboard` | Placeholder — no aggregation endpoint exists; must not show fake metrics |
| Operations | `/operations`, `/operations/[id]` | `GET /api/service-requests/`, `GET /api/service-requests/{id}/` — real |
| Document Center | `/documents` | Placeholder in this slice — see §5 |
| Automation → Rules | `/automation/rules`, `/automation/rules/[id]` | `GET /api/rules/`, `GET /api/rules/metadata/` — real |

**Explicitly not shown:** Customers, Vessels, Organizations, and
Administration master-data screens. The backend now has the tenant catalog
and operation-template API, but this frontend slice does not add their
administration screens. Workflow instance screens remain read-only.

**Frontend navigation visibility is never treated as authorization.**
Hiding a sidebar item is a UX/scope decision, not a security boundary. The
backend's `IsTenantMember`/`IsSameTenantObject` permission classes remain
the only real authority over what data is accessible (verified in
`backend/config/permissions.py`).

Current backend update: tenant catalog and operation-template endpoints now
exist under `flag-relationships`, `service-offerings`,
`operation-templates`, `operation-template-versions`,
`checklist-templates`, and `workflow-step-templates`. They are API-ready but
their administration screens remain outside this frontend slice.

## 3. Route hierarchy — DECIDED for Phase 1, rest deferred

```
/dashboard                              placeholder (Stage 3)
/operations                             real data (Stage 4)
/operations/[serviceRequestId]          real data (Stage 4)
/documents                              placeholder (Stage 3)
/automation/rules                       placeholder (Stage 3)
/automation/rules/[ruleId]              placeholder (Stage 3)
```

No tenant ID embedded in any URL — the backend resolves tenant from the
authenticated session (`request.user.tenant`), never from a URL parameter;
the frontend mirrors that.

All routes not listed above (Directory, Administration, customer portal) are
**deferred** — not routed, not linked, not present in the sidebar.

## 4. Shared operational model — DECIDED

- One global list at `/operations` — no per-module duplicate lists in this slice.
- **Update (frontend pagination/filtering sprint):** `/operations` now consumes the paginated `ServiceRequestViewSet` list (`{count, next, previous, results}`) with real pagination, search, and ordering wired to the URL query string. Query-parameter support is **three-tiered** — do not assume backend support implies a frontend control, or that a frontend control implies every backend capability is exposed:

  | Param | Backend support | Frontend status |
  |---|---|---|
  | `page`, `page_size` | Yes (`StandardResultsPagination`, max 100) | **Exposed** — Previous/Next links; sanitized (non-numeric/non-positive values are dropped, never forwarded) |
  | `status` | Yes (`filterset_fields`) | **Exposed** — dropdown restricted to the closed `ServiceRequest.Status` set; any other value is dropped, not forwarded |
  | `search` | Yes (`SearchFilter`) | **Exposed** — free-text box |
  | `ordering` | Yes (`OrderingFilter`, 4 fields) | **Exposed** — dropdown restricted to the backend's approved `ordering_fields`; anything else is dropped |
  | `customer`, `vessel`, `service_type`, `flag` | Yes (`filterset_fields`) | **Deferred — not read from the URL, not forwarded to the backend, no UI control.** The list response only ever returns `customer_name`/`vessel_name`/`service_type_name`/`flag_name` as flat strings, never an id, and no Customers/Vessels/Catalog list endpoint exists yet to resolve a display name to the id these filters need. Accepting a raw id from a public URL with no UI affordance to set it correctly, and no way to validate it client-side, would expose backend capability this frontend cannot yet present safely. Revisit once a Directory (Customers/Vessels) or Catalog list endpoint exists. |

  The exact whitelist lives in `app/operations/page.tsx::buildSanitizedQuery()` — a single sanitized `URLSearchParams`, shared by the backend fetch and by `PaginationControls`' generated links, so a page-2 link can never carry a param (or an invalid value) the fetch itself wouldn't also send.
- `catalog.ServiceType` still has **no `module` field** — a module filter specifically remains unimplemented, since that concept doesn't exist in the backend yet (unrelated to the customer/vessel/service_type/flag deferral above, which is an id-resolution problem, not a missing-concept problem).
- Module/type indicator: `service_type_name` and `flag_name`, exactly as returned by `ServiceRequestListSerializer` — no invented grouping.
- Module-specific detail extends the shared `ServiceRequest` detail page as future tabs/sections — not built in this slice, not designed here (per standing constraint: no Crew/Survey/Flag/PM domain content).

## 5. List / drawer / modal / full-page rules — DECIDED for what's built

- **Service Request detail is a full page** (`/operations/[id]`), not a drawer — confirmed product decision.
- Document preview and lightweight related-item inspection **may later use drawers** — not built in this slice.
- Quick-create and destructive-confirmation patterns from the earlier proposal remain the target shape but are **not implemented** — no create/delete flow exists in this read-only slice.

## 6. Screen inventory — Phase 1 actual state

| Screen | State in this slice |
|---|---|
| Dashboard | Restrained placeholder — no fake metrics, no fake records |
| Operations list | Real data from `GET /api/service-requests/` |
| Operations detail — Overview | Real data from `GET /api/service-requests/{id}/` |
| Operations detail — Activity | Real data from `GET /api/service-requests/{id}/timeline/` |
| Operations detail — Checklist | Real data from `GET /api/checklist-items/?service_request={id}` (verified: this filter is genuinely supported server-side) |
| Operations detail — Workflow | Real data from `GET /api/workflow-steps/?service_request={id}` (verified: this filter is genuinely supported server-side) |
| Operations detail — Documents | Real data from `GET /api/documents/?service_request={id}`; the detail page renders the tenant-scoped filtered document list. |
| Document Center | Restrained placeholder |
| Automation → Rules list/detail | Restrained placeholder in this slice (the real `/api/rules/` and `/api/rules/metadata/` endpoints exist and work, but building the Rules UI itself is out of scope for this implementation slice — see product decision ordering) |
| Customers / Vessels / Organizations / Administration | Deferred — no frontend screen |
| Tenant Catalog / Operation Templates | Backend/API ready; frontend administration screen deferred |
| Customer portal | Deferred — undecided hosting model |

## 7. Navigation behavior — DECIDED

- A hidden sidebar item means "no frontend screen for this yet," never "you're not allowed." The two concepts are independent, and today the backend only enforces the first: tenant membership. Per-role restriction (`User.role`) exists on the model but is **not enforced** by any endpoint — confirmed by reading every permission class in `backend/config/permissions.py`. Any future frontend role-based hiding must be documented as cosmetic, not a security boundary, until backend enforcement exists.

## 8. Deferred (explicitly out of scope for this slice)

- Global search, command palette, saved filters, recent records
- Dashboard metrics beyond restrained placeholders
- Customers, Vessels, Organizations, Administration, Workflow Templates screens
- Any Crew/Survey/Flag Registration/Project Management domain content
- Tenant branding, dark mode
- Customer portal (hosting model undecided)
- Create/edit/delete flows for Service Requests (this slice is read-only)

## 9. Needs confirmation

- Whether `ServiceType` should formally gain a `module` field (blocks any future module filter on Operations).
- Priority/build order for the missing backend endpoints (Customers, Vessels, Organizations, Users, Catalog).
- Customer portal hosting model (same app vs. separate app).

## 10. Catalog and document detail update

The backend now exposes tenant-scoped flag relationships, service offerings,
operation templates, and version management under the catalog/process API.
There is intentionally no broad management UI in this slice because the
frontend has no existing operation-create form or template administration
surface.

The Operations detail Documents tab is now connected to
`GET /api/documents/?service_request={id}`. The old section 6 placeholder
description predates that backend filter and should be read as superseded by
this current behavior.
