"""
Example: the rule from the brief —

    WHEN:  Document classified as "BlueCard"
    IF:    ServiceType = OwnerChange
    THEN:  Activate "Bunker" workflow step

Not a management command or migration — just a plain, runnable example
showing how a rule is actually constructed against this schema. A future
admin UI would produce exactly this shape from a form.
"""
from catalog.models import DocumentType, ServiceType
from rules.models import Rule
from tenants.models import Tenant


def create_bluecard_bunker_rule(tenant: Tenant) -> Rule:
    owner_change = ServiceType.objects.get(code="owner_change")
    bluecard = DocumentType.objects.get(code="bluecard")

    return Rule.objects.create(
        tenant=tenant,
        name="Auto-activate Bunker step on Blue Card (Owner Change)",
        description=(
            "When a Blue Card is classified on an Owner Change case, the "
            "Bunker workflow step is activated automatically instead of "
            "waiting on a staff member to notice P&I cover is confirmed."
        ),
        event_type="document.classified",
        conditions=[
            {"field": "document_type", "operator": "eq", "value": bluecard.code},
            {"field": "service_type", "operator": "eq", "value": owner_change.code},
        ],
        action_type=Rule.ActionType.ACTIVATE_WORKFLOW_STEP,
        action_config={"step_code": "bunker"},
        is_active=True,
        priority=0,
    )


# What happens at runtime, end to end:
#
# 1. Staff (or, later, an AI classifier) calls
#    documents.services.classify_document(document=doc, document_type=bluecard, ...)
# 2. That emits DOCUMENT_CLASSIFIED with the document, its ServiceRequest,
#    previous/new checklist_item, etc.
# 3. checklists/listeners.py recomputes checklist items (unrelated to
#    rules -- it's just another subscriber to the same event).
# 4. rules/listeners.py's registration means rules.services.evaluate_rules
#    also fires. It resolves facts: {"document_type": "bluecard",
#    "service_type": "owner_change", "flag": "panama", ...} via
#    rules/facts.py.
# 5. It fetches this tenant's active Rules for event_type="document.classified",
#    finds the one above, evaluates its two conditions -- both match.
# 6. It executes activate_workflow_step with {"step_code": "bunker"},
#    which calls the REAL workflow.services.update_step_status(...) --
#    running the actual state-machine guard, not a rule-engine shortcut.
#    If the Bunker step is still BLOCKED (its own dependencies unmet),
#    this raises InvalidStepTransitionError, which is caught, recorded
#    in RuleExecutionLog as a failure, and logged to the case timeline
#    via RULE_ACTION_FAILED -- the classification itself still succeeds.
# 7. On success, update_step_status itself emits WORKFLOW_STEP_STATUS_CHANGED,
#    which activity/listeners.py logs normally -- indistinguishable in the
#    timeline from a human clicking "activate" on that step.
