"""
Action execution: `Rule.action_type` + `Rule.action_config` -> one of
the functions below.

THE CENTRAL SAFETY RULE OF THIS FILE: every action function calls an
EXISTING service-layer function (`workflow.services.update_step_status`,
`service_requests.services.transition_state`,
`organizations.services.attach_organization_to_service_request`,
`activity.services.log_activity`) — none of them touch a model's
`.save()` directly. This means a Rule literally CANNOT bypass any
invariant, guard condition, or event emission that a human-initiated
action would go through: activating a workflow step via a Rule runs the
exact same `assert_step_transition_allowed` check as a staff member
clicking a button would. The rule engine adds a NEW WAY TO CALL the
service layer; it does not add a new way to mutate the domain.

Each function raises on failure (invalid transition, object not found,
bad config) rather than swallowing errors — `rules/services.py` is
responsible for catching these per-rule so one misconfigured rule can't
take down the whole event dispatch; these functions themselves stay
simple and fail loud.
"""
from activity.services import log_activity
from service_requests.models import ServiceRequest


class ActionConfigError(Exception):
    """action_config is missing a required key or references something
    that doesn't exist — a Rule authoring problem."""


def _require(config: dict, key: str):
    if key not in config:
        raise ActionConfigError(f"action_config missing required key '{key}'")
    return config[key]


def activate_workflow_step(*, service_request: ServiceRequest, action_config: dict, rule) -> None:
    """action_config: {"step_code": "bunker"}"""
    from workflow.models import WorkflowStepInstance
    from workflow.services import update_step_status

    step_code = _require(action_config, "step_code")
    step_filter = {"step_template__code": step_code}
    if service_request.operation_template_version_id:
        step_filter["step_template__operation_template_version_id"] = service_request.operation_template_version_id
    else:
        step_filter.update({
            "step_template__operation_template_version__isnull": True,
            "step_template__service_type_id": service_request.service_type_id,
        })
    try:
        step_instance = service_request.workflow_steps.get(**step_filter)
    except WorkflowStepInstance.DoesNotExist:
        raise ActionConfigError(
            f"ServiceRequest {service_request.reference_code} has no workflow step "
            f"with code '{step_code}' (check the step exists for this ServiceType/Flag)."
        )
    # update_step_status runs the SAME guard (workflow.state_machine) a
    # human-initiated transition would — e.g. a step still BLOCKED on an
    # unmet dependency will correctly reject this with
    # InvalidStepTransitionError, which propagates up and is recorded as
    # a failed rule execution, not silently forced through.
    update_step_status(step_instance=step_instance, status=WorkflowStepInstance.Status.ACTIVE, actor_user=None)


def change_service_request_state(*, service_request: ServiceRequest, action_config: dict, rule) -> None:
    """action_config: {"target_status": "in_progress"}"""
    from service_requests.services import transition_state

    target_status = _require(action_config, "target_status")
    # transition_state runs the full guard registry (checklist-complete
    # for Ready, workflow-closed for Completed, etc.) — a Rule cannot
    # force a ServiceRequest into Completed early just because its
    # action_config says so.
    transition_state(service_request=service_request, target_status=target_status, actor_user=None)


def assign_organization(*, service_request: ServiceRequest, action_config: dict, rule) -> None:
    """action_config: {"organization_id": 12, "role": "pni_club"}"""
    from organizations.models import Organization
    from organizations.services import attach_organization_to_service_request

    organization_id = _require(action_config, "organization_id")
    role = _require(action_config, "role")
    try:
        organization = Organization.objects.get(id=organization_id, tenant=service_request.tenant)
    except Organization.DoesNotExist:
        raise ActionConfigError(
            f"Organization {organization_id} not found for tenant {service_request.tenant_id} "
            f"(cross-tenant references are rejected, not just missing ids)."
        )
    # Runs the SAME role/organization_type consistency check added in
    # the collaboration-domain hardening pass — a Rule can't attach a
    # law firm as a FLAG_AUTHORITY any more than a human user could.
    attach_organization_to_service_request(
        service_request=service_request, organization=organization, role=role, actor_user=None,
    )


def create_activity_log_entry(*, service_request: ServiceRequest, action_config: dict, rule) -> None:
    """action_config: {"summary": "...", "metadata": {...}}  (both optional)"""
    log_activity(
        tenant=service_request.tenant,
        verb="rule.note",
        entity_type="service_request",
        entity_id=service_request.id,
        service_request=service_request,
        actor_type="system",
        summary=action_config.get("summary") or f"Rule '{rule.name}' fired",
        metadata=action_config.get("metadata", {}),
    )


ACTIONS = {
    "activate_workflow_step": activate_workflow_step,
    "change_service_request_state": change_service_request_state,
    "assign_organization": assign_organization,
    "create_activity_log_entry": create_activity_log_entry,
}

# Used by rules/serializers.py to reject an obviously-broken
# action_config at RULE-SAVE time (missing a required key) rather than
# only discovering it the first time the rule actually fires — cheap
# validation that meaningfully shortens the feedback loop for whoever
# (today: an engineer seeding rules; later: an admin UI) is authoring
# rules.
ACTION_REQUIRED_CONFIG_KEYS = {
    "activate_workflow_step": {"step_code"},
    "change_service_request_state": {"target_status"},
    "assign_organization": {"organization_id", "role"},
    "create_activity_log_entry": set(),
}
