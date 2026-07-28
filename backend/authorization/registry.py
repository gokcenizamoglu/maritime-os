"""
Platform-defined capability registry — the single source of truth for
what capabilities exist. Database rows (authorization.Capability) are
synchronized FROM this registry, never the other way around.

Every entry here corresponds to a real, existing backend action. Do not
add speculative capabilities for endpoints or modules that do not exist
yet — when the endpoint is built, the capability is added here in the
same sprint.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityDef:
    code: str
    label: str
    description: str
    category: str
    module_code: str


CAPABILITY_REGISTRY: dict[str, CapabilityDef] = {}


def _r(code: str, label: str, description: str, category: str, module_code: str) -> None:
    CAPABILITY_REGISTRY[code] = CapabilityDef(
        code=code, label=label, description=description,
        category=category, module_code=module_code,
    )


# Tenant catalog / process configuration
_r("tenant_catalog.view", "View Tenant Catalog",
   "View tenant flag relationships and service offerings.",
   "tenant_catalog", "core")

_r("tenant_catalog.manage", "Manage Tenant Catalog",
   "Create and update tenant flag relationships and service offerings.",
   "tenant_catalog", "core")

_r("operation_template.view", "View Operation Templates",
   "View tenant operation templates, versions, and definitions.",
   "operation_templates", "core")

_r("operation_template.manage", "Manage Operation Templates",
   "Create and edit operation templates and draft definitions.",
   "operation_templates", "core")

_r("operation_template.publish", "Publish Operation Templates",
   "Publish, clone, and retire operation template versions.",
   "operation_templates", "core")


# ---------------------------------------------------------------------------
# Service Requests — ServiceRequestViewSet
# list/retrieve, create + transition
# No generic update/delete (http_method_names excludes PATCH/PUT/DELETE)
# ---------------------------------------------------------------------------
_r("service_request.view", "View Service Requests",
   "List and view service request details.",
   "service_requests", "core")

_r("service_request.create", "Create Service Requests",
   "Create new service requests.",
   "service_requests", "core")

_r("service_request.update", "Update Service Requests",
   "Trigger validated ServiceRequest state transitions.",
   "service_requests", "core")

# ---------------------------------------------------------------------------
# Documents — DocumentViewSet
# list/retrieve, create (internal upload), classify action
# No general update/delete (http_method_names = ["get", "post"])
# ---------------------------------------------------------------------------
_r("document.view", "View Documents",
   "List and view uploaded documents.",
   "documents", "core")

_r("document.create", "Upload Documents",
   "Upload documents to a service request (internal staff upload).",
   "documents", "core")

_r("document.classify", "Classify Documents",
   "Assign or change a document's type classification.",
   "documents", "core")

# ---------------------------------------------------------------------------
# Checklists — ChecklistItemViewSet (ReadOnlyModelViewSet)
# list/retrieve only, zero write actions
# ---------------------------------------------------------------------------
_r("checklist.view", "View Checklists",
   "View checklist items and completion status.",
   "checklists", "core")

# ---------------------------------------------------------------------------
# Workflow — WorkflowStepInstanceViewSet (ReadOnly + transition action)
# ---------------------------------------------------------------------------
_r("workflow.view", "View Workflow Steps",
   "List and view workflow step instances.",
   "workflow", "core")

_r("workflow.advance", "Advance Workflow Steps",
   "Transition workflow steps between statuses.",
   "workflow", "core")

# ---------------------------------------------------------------------------
# Rules — RuleViewSet (full ModelViewSet)
# list/retrieve/metadata, create, update/partial_update, destroy
# ---------------------------------------------------------------------------
_r("rule.view", "View Rules",
   "List, view, and inspect rule metadata.",
   "rules", "core")

_r("rule.create", "Create Rules",
   "Create new automation rules.",
   "rules", "core")

_r("rule.update", "Update Rules",
   "Edit existing automation rules.",
   "rules", "core")

_r("rule.delete", "Delete Rules",
   "Delete automation rules.",
   "rules", "core")

# ---------------------------------------------------------------------------
# Activity / Timeline — ServiceRequestTimelineView (GET only)
# ---------------------------------------------------------------------------
_r("activity.view", "View Activity Timeline",
   "View service request activity timeline.",
   "activity", "core")

# ---------------------------------------------------------------------------
# Derived sets used by default role provisioning
# ---------------------------------------------------------------------------
VIEW_ONLY_CAPABILITIES = frozenset(
    code for code, cap in CAPABILITY_REGISTRY.items()
    if code.endswith(".view")
)

ALL_CAPABILITIES = frozenset(CAPABILITY_REGISTRY.keys())

# Operations can run cases and inspect configuration. Catalog/template
# ownership and publication stay with Tenant Admin (or an explicitly
# assigned custom role), so a daily operator cannot change the recipe used
# by future work.
OPS_CAPABILITIES = frozenset(
    code for code in CAPABILITY_REGISTRY
    if not code.startswith("rule.")
    and code not in {
        "tenant_catalog.manage",
        "operation_template.manage",
        "operation_template.publish",
    }
)
