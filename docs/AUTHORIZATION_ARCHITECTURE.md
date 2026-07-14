# Authorization Architecture

MaritimeOS uses a capability-based RBAC system where capabilities are
platform-defined and roles are tenant-owned.

## Core Concepts

### Capabilities

Capabilities are the atomic units of authorization. Each capability maps
to a specific action on a specific resource (e.g. `service_request.create`).

- **Platform-defined**: capabilities originate from a code registry
  (`authorization/registry.py`), never from tenant input.
- **DB-synchronized**: a `Capability` model holds database rows for
  relational assignment, admin UI, and future reporting.
- **Immutable codes**: capability codes are stable identifiers. They
  are never mutated in normal workflows.

Sync mechanism: `python manage.py sync_capabilities` (or call
`authorization.services.sync_capabilities()` directly).

### Tenant Roles

Each tenant creates and manages its own roles. A role belongs to exactly
one tenant. Role names are unique within a tenant but different tenants
may use identical names.

Three system-default roles are provisioned for each tenant:

| Role           | Capabilities                                |
|----------------|---------------------------------------------|
| Tenant Admin   | All active capabilities                     |
| Operations     | All except rule management (create/update/delete) |
| Viewer         | All `.view` capabilities only               |

Provisioning: `authorization.services.provision_default_roles(tenant)`.
Idempotent — safe to call multiple times.

### RoleCapability (join model)

A relational join between `TenantRole` and `Capability`. No JSON arrays.
Deleting a role cascades to `RoleCapability` but never to `Capability`.

### UserRoleAssignment

A user may hold multiple roles within their tenant. Effective
capabilities are the **union** of all assigned role capabilities.

Cross-tenant assignments are rejected at the service layer
(`authorization.services.assign_role()`).

## Authorization Flow

```
Request arrives
  → IsTenantMember: is user authenticated with a tenant?
  → IsSameTenantObject: does the object belong to the user's tenant?
  → HasCapability: does the user hold the required capability?
```

All three checks are independent and layered. `HasCapability` never
replaces the existing tenant isolation — it adds a capability gate
on top of it.

## Capability Map (current)

| Endpoint                         | Action              | Capability              |
|----------------------------------|----------------------|-------------------------|
| ServiceRequestViewSet            | list, retrieve       | service_request.view    |
| ServiceRequestViewSet            | create               | service_request.create  |
| ServiceRequestViewSet            | partial_update       | service_request.update  |
| ServiceRequestViewSet            | transition           | service_request.update  |
| DocumentViewSet                  | list, retrieve       | document.view           |
| DocumentViewSet                  | create               | document.create         |
| DocumentViewSet                  | classify             | document.classify       |
| ChecklistItemViewSet             | list, retrieve       | checklist.view          |
| WorkflowStepInstanceViewSet      | list, retrieve       | workflow.view           |
| WorkflowStepInstanceViewSet      | transition           | workflow.advance        |
| RuleViewSet                      | list, retrieve, meta | rule.view               |
| RuleViewSet                      | create               | rule.create             |
| RuleViewSet                      | update               | rule.update             |
| RuleViewSet                      | destroy              | rule.delete             |
| ServiceRequestTimelineView       | get                  | activity.view           |

### Rule Execution

Rule execution (`rules/services.py::evaluate_rules`) runs with
`actor_user=None`. It does NOT require any human user capability.
Authorization applies to rule authoring and management, not automated
execution.

## DRF Permission Class

```python
from authorization.permissions import HasCapability

class MyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "resource.view",
        "create": "resource.create",
    }
```

For views with a single capability across all actions:

```python
class MyView(APIView):
    permission_classes = [IsTenantMember, HasCapability]
    required_capability = "activity.view"
```

## Policy Functions

```python
from authorization.services import user_effective_capabilities, user_has_capability

caps = user_effective_capabilities(user)  # frozenset of codes
can = user_has_capability(user, "document.create")  # bool
```

Both functions are independent of DRF request objects.

## /api/auth/me/ Response

```json
{
  "id": 1,
  "username": "ops-user",
  "first_name": "Ops",
  "last_name": "User",
  "role": "ops",
  "tenant": {"id": 1, "name": "Liva Marine"},
  "roles": [{"id": 5, "name": "Operations"}],
  "capabilities": ["checklist.view", "document.classify", "document.create", ...]
}
```

- `role` (string): temporary field from `User.role`, kept for this
  transition sprint. Will be removed once all frontend code migrates
  to `capabilities`.
- `roles`: display-only. Frontend must never branch on role names.
- `capabilities`: sorted array of effective capability codes.

## What This System Is NOT

### Not tenant module entitlement
Module entitlement ("does this tenant have the Survey module?") is a
separate concern, enforced at a different layer. Capabilities control
what a user can do within modules they have access to.

### Not platform-level users
Platform support, auditor, and admin users are deferred. The current
system handles internal staff within a single tenant.

### Not customer portal authorization
Customer portal users (external customers uploading documents via
tokenized links) are a separate authorization domain with different
identity and access patterns.

## Temporary State: User.role

`User.role` (CharField with choices admin/ops/viewer) is the pre-RBAC
authorization field. It is NOT removed in this sprint to avoid a
breaking migration while the frontend transitions.

The data migration maps existing values:
- `admin` → UserRoleAssignment to "Tenant Admin"
- `ops` → UserRoleAssignment to "Operations"
- `viewer` → UserRoleAssignment to "Viewer"

### Future removal plan
1. Frontend stops reading `user.role`, uses `capabilities` instead.
2. Remove `role` field from `AuthenticatedUserSerializer.from_user()`.
3. Remove `User.role` field and generate a schema migration.

## Future: OperationTemplate and Module Catalog

When `OperationTemplate` is implemented (Sprint 2+), it will interact
with authorization in two ways:

1. **Module entitlement**: `TenantModuleEntitlement` controls which
   modules a tenant has access to. `OperationTemplate.module` references
   the module catalog.
2. **Operation-level permissions**: `OperationTemplate` may define which
   capabilities or roles are required to create/manage operations of that
   type, using the same `Capability` rows defined here.

The capability registry will grow as new endpoints and modules are
added — each capability is added in the same sprint as the endpoint it
gates.

## Why Role Names Are Never Used for Authorization

Role names are tenant-defined display labels. Two tenants may define
"Manager" with completely different capability sets. Authorization
decisions always go through capability codes, never role name comparison.
This is enforced architecturally: `HasCapability` checks capability
codes via the policy layer, and there is no `HasRole("name")` permission
class.
