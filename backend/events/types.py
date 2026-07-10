"""
Domain event name constants.

Kept as plain strings (not an enum consumed everywhere) so that logging
and any future message-bus payload can serialize `event.name` directly
without an extra `.value` unwrap — but centralized here so every emitter
and listener imports the same constant instead of hand-typing strings
that could silently drift (`"document.classified"` vs
`"document_classified"` would otherwise fail SILENTLY — a listener just
never fires, with no error anywhere).
"""

# Document domain
DOCUMENT_UPLOADED = "document.uploaded"
DOCUMENT_CLASSIFIED = "document.classified"
DOCUMENT_SUPERSEDED = "document.superseded"

# Checklist domain
CHECKLIST_ITEM_COMPLETION_CHANGED = "checklist_item.completion_changed"

# Process domain
SERVICE_REQUEST_CREATED = "service_request.created"
SERVICE_REQUEST_STATUS_CHANGED = "service_request.status_changed"
WORKFLOW_STEP_STATUS_CHANGED = "workflow_step.status_changed"

# Collaboration domain
ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST = "service_request_organization.attached"

# Rule engine (introduced alongside the `rules` app — see rules/README
# for why these are separate from the domain events above: they
# describe the RULE ENGINE's own behavior, not a business fact)
RULE_ACTION_EXECUTED = "rule.action_executed"
RULE_ACTION_FAILED = "rule.action_failed"

# Event types a Rule is allowed to trigger on. Deliberately a whitelist,
# not "any string in events.types" — a Rule referencing an event name
# that isn't wired to the rule engine's listener would silently never
# fire, which is a worse failure mode than rejecting it at save time.
RULE_TRIGGERABLE_EVENT_TYPES = [
    DOCUMENT_UPLOADED,
    DOCUMENT_CLASSIFIED,
    DOCUMENT_SUPERSEDED,
    CHECKLIST_ITEM_COMPLETION_CHANGED,
    SERVICE_REQUEST_CREATED,
    SERVICE_REQUEST_STATUS_CHANGED,
    WORKFLOW_STEP_STATUS_CHANGED,
    ORGANIZATION_ATTACHED_TO_SERVICE_REQUEST,
]
