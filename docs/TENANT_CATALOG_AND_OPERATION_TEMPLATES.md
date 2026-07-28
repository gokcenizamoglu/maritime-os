# Tenant Catalog and Versioned Operation Templates

MaritimeOS keeps global maritime vocabulary separate from tenant-owned
availability and process configuration.

## Domain separation

```text
Flag / ServiceType / DocumentType / OrganizationType
                         |
             TenantFlagRelationship
                         |
             TenantServiceOffering
                         |
                  OperationTemplate
                         |
               OperationTemplateVersion
                 /                    \
       ChecklistTemplate       WorkflowStepTemplate
                 \                    /
                    ServiceRequest
                 /                    \
       ChecklistItem              WorkflowStepInstance
```

`Flag`, `ServiceType`, `DocumentType`, and `OrganizationType` remain global
catalog records. Their existence does not grant any tenant access.

`TenantFlagRelationship` answers which registry, authority, correspondent, or
partner network a tenant works with. It is tenant-scoped, can have multiple
rows for the same flag, and carries status and validity dates. Organization
references are validated against the same tenant by the service layer.

`TenantServiceOffering` answers which service a tenant actually accepts. A
flag-bound offering references both the global flag and an active relationship.
An unflagged offering is allowed only for `OPTIONAL` or `NOT_APPLICABLE`
service types. An offering can be inactive or stop accepting new requests
without affecting existing ServiceRequests.

Existing code and data model history require a flag for the currently known
service types, so the migration defaults `ServiceType.flag_scope` to
`REQUIRED`. No existing service was inferred as flag-independent. Product or
admin configuration can explicitly choose `OPTIONAL` or `NOT_APPLICABLE` for a
new service type after that business rule is confirmed.

`OperationTemplate` is a process variant, not a service catalog entry. One
offering may have Standard, Express, or other variants. `is_default` is
maintained per offering and protected by a database constraint.

`OperationTemplateVersion` is the immutable process recipe. Drafts are edited,
published versions are used for new operations, and published versions may be
retired or archived. Publishing retires the previous published version in the
same transaction. Checklist and workflow definitions belong to a version, so
new versions never rewrite existing ServiceRequests.

Published, retired, and archived versions are protected at the application
ORM boundary: instance `save/delete`, queryset `update/delete`,
`bulk_update/bulk_create`, versioned checklist/workflow definitions, and the
workflow dependency through model all enforce the lifecycle rule. Draft
definitions remain editable. Publication, retirement, archiving, cloning, and
dependency changes for drafts go through the workflow services. This is an
application-layer guarantee; it does not claim to protect an operator who
intentionally bypasses Django ORM with raw SQL or an unregistered database
manager.

## ServiceRequest creation

The preferred payload is:

```json
{
  "customer": 12,
  "vessel": 34,
  "service_offering": 7,
  "operation_template": 11
}
```

`operation_template` is optional. When omitted, the active default template
for the offering is selected. The template must have a published version.
The create service stores both `service_offering` and
`operation_template_version` on the ServiceRequest, then creates checklist and
workflow instances from that exact version inside one transaction.

After creation, ServiceRequest catalog relations, customer/vessel identity,
service type, flag, and status are immutable through the API. There is no
generic PUT/PATCH route. Status changes use
`POST /api/service-requests/{id}/transition/`, which runs the state machine and
emits `service_request.status_changed` for the activity timeline and rules.

The temporary legacy payload is:

```json
{
  "customer": 12,
  "vessel": 34,
  "service_type": 3,
  "flag": 5
}
```

It is resolved only when exactly one active, valid, accepting offering exists
for that tenant and pair. There is no global template fallback. Ambiguous or
missing matches return a validation error.

## API surface

Tenant catalog:

- `GET/POST/PATCH /api/flag-relationships/`
- `GET/POST/PATCH /api/service-offerings/`
- `GET /api/service-offerings/available/`
- `POST /api/service-offerings/{id}/accept-new-requests/`

Process configuration:

- `GET/POST/PATCH /api/operation-templates/`
- `GET /api/operation-templates/{id}/versions/`
- `POST /api/operation-templates/{id}/create-draft/`
- `POST /api/operation-templates/{id}/set-default/`
- `GET /api/operation-template-versions/`
- `POST /api/operation-template-versions/{id}/clone/`
- `POST /api/operation-template-versions/{id}/publish/`
- `POST /api/operation-template-versions/{id}/retire/`
- `POST /api/operation-template-versions/{id}/archive/`
- `GET/POST/PATCH/DELETE /api/checklist-templates/`
- `GET/POST/PATCH/DELETE /api/workflow-step-templates/`

Definition endpoints require a draft version. Workflow dependencies are
submitted as stable `depends_on_codes` and are checked for same-version
membership and cycles before publish.

All endpoints filter by the authenticated tenant, apply object-level tenant
permissions, and require capability-based authorization. Tenant Admin owns
catalog management and template publication. Operations can view catalog and
templates and run daily operations, but cannot manage or publish templates
through the default role. A custom tenant role may receive those capabilities.

## Existing operations and migration

The data migration does not copy every global service/flag combination to
every tenant. For each existing ServiceRequest it:

1. Creates or reuses a direct flag relationship.
2. Creates an inactive, non-accepting offering for the historical pair.
3. Creates an inactive legacy OperationTemplate and its first published version.
4. Copies the matching global checklist/workflow definitions into that version.
5. Rebinds existing checklist and workflow instances to the copied definitions.
6. Stores the offering and version on the existing ServiceRequest without
   changing instance status or completion state.

Backfilled rows are explicitly historical because current availability cannot
be inferred safely from a past operation. A tenant administrator must activate
an offering and relationship after confirming the current business setup.
Tenants with no historical operation receive no inferred offering.

The migration is idempotent for the historical identity it creates and uses
stable service/flag codes and workflow step codes rather than database ID
ordering. The reverse migration is intentionally a no-op so a rollback does
not delete operational history or configuration created after deployment.

Before applying the historical backfill, run the read-only gate:

```text
python manage.py preflight_operation_catalog
```

It reports safe, warning, and blocking categories with counts and database
IDs only. It checks flagless historical rows without inferring a flag scope,
stable-code collisions, truncated codes, missing dependencies, workflow
cycles, invalid tenant references, ambiguous active offerings, and accepting
offerings without a published default. A blocking result exits non-zero. If
the migration is already applied, the command explicitly reports that it is a
current-state audit rather than a retroactive migration gate.

## Event and automation behavior

The existing chain remains unchanged:

```text
Document classified
  -> DOCUMENT_CLASSIFIED
  -> checklist instance recompute
  -> activity timeline entry
  -> rule evaluation
  -> service-layer action
  -> workflow or ServiceRequest transition
```

Checklist recompute reads only the ServiceRequest's instances and excludes
superseded documents. Rule actions resolve `step_code` inside the triggering
ServiceRequest's `operation_template_version`; another tenant or another
version with the same code cannot be selected. Deactivating an offering or
relationship does not block document, checklist, workflow, or activity work
on an existing ServiceRequest.
