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

**Explicitly not shown:** Customers, Vessels, Organizations, Administration,
Workflow Templates. Confirmed by reading the backend: `config/urls.py`
registers exactly five routers (`service-requests`, `documents`,
`checklist-items`, `workflow-steps`, `rules`) plus the timeline endpoint and
the public upload endpoint. There is no `CustomerViewSet`, `VesselViewSet`,
`OrganizationViewSet`, `UserViewSet`, or catalog/entitlement endpoint
anywhere in the codebase, and no `WorkflowStepTemplate` endpoint (only
`WorkflowStepInstance` is exposed, read-only). These sidebar items will be
added when — and only when — their backend endpoints exist.

**Frontend navigation visibility is never treated as authorization.**
Hiding a sidebar item is a UX/scope decision, not a security boundary. The
backend's `IsTenantMember`/`IsSameTenantObject` permission classes remain
the only real authority over what data is accessible (verified in
`backend/config/permissions.py`).

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
- Verified backend reality: **the list endpoint returns no `module` field and no query-param filtering of any kind** (`ServiceRequestViewSet` has no `filter_backends`, `filterset_fields`, `search_fields`, or `ordering_fields` configured, and `catalog.ServiceType` has no `module` field). A module filter is **not implemented** in this slice — it would imply server support that does not exist.
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
| Operations detail — Documents | **Not connected in this slice** — `DocumentViewSet` has no `service_request` query-param filter; fetching and client-filtering the tenant's entire document list would not be a safe/correct data flow. Shown as an honest "not connected" state, not mock data. |
| Document Center | Restrained placeholder |
| Automation → Rules list/detail | Restrained placeholder in this slice (the real `/api/rules/` and `/api/rules/metadata/` endpoints exist and work, but building the Rules UI itself is out of scope for this implementation slice — see product decision ordering) |
| Customers / Vessels / Organizations / Administration / Workflow Templates | Deferred — no backend endpoint |
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
