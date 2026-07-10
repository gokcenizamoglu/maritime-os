"""
Explicit state transition graph AND guard conditions for
ServiceRequest.status.

ARCHITECTURAL CHANGE: the graph (ALLOWED_TRANSITIONS) alone answers
"is Draft -> Ready a legal EDGE in the state diagram". It does NOT
answer "has this SPECIFIC ServiceRequest actually earned that move" —
e.g. the graph says Draft -> CollectingDocuments -> Ready is legal, but
nothing stopped a caller from moving a request to Ready with zero
checklist items satisfied. GUARDS below close that gap: each is a
function of (service_request, target_status) that raises if the
domain-level precondition for that specific move isn't met. This is
what "model state as a domain concept, not a free string" means in
practice — the state machine now encodes not just WHICH moves exist,
but WHEN they're actually valid for a given case.

Kept as plain data structures (not django-fsm or a third-party lib) so
the Phase 1 team isn't locked into a dependency decision, but structured
so swapping in django-fsm later is a mechanical change — the graph and
guards are exactly what `@transition(conditions=[...])` would encode.
"""
from service_requests.models import ServiceRequest

Status = ServiceRequest.Status

ALLOWED_TRANSITIONS = {
    Status.DRAFT: {Status.COLLECTING_DOCUMENTS},
    Status.COLLECTING_DOCUMENTS: {Status.READY, Status.WAITING_EXTERNAL},
    Status.READY: {Status.IN_PROGRESS, Status.COLLECTING_DOCUMENTS},
    Status.IN_PROGRESS: {Status.WAITING_EXTERNAL, Status.COMPLETED, Status.COLLECTING_DOCUMENTS},
    Status.WAITING_EXTERNAL: {Status.IN_PROGRESS, Status.COMPLETED},
    Status.COMPLETED: set(),  # terminal
}


class InvalidTransitionError(Exception):
    """The target status is not a legal edge from the current status."""


class TransitionGuardError(Exception):
    """The edge is legal, but this specific ServiceRequest hasn't
    satisfied the domain precondition for it yet."""


def _guard_ready_requires_complete_checklist(service_request: ServiceRequest, target_status: str) -> None:
    if target_status != Status.READY:
        return
    from checklists.services import get_checklist_progress
    progress = get_checklist_progress(service_request)
    if progress["total"] > 0 and progress["complete"] < progress["total"]:
        raise TransitionGuardError(
            f"Cannot move {service_request.reference_code} to Ready: "
            f"checklist is {progress['complete']}/{progress['total']} complete."
        )


def _guard_completed_requires_closed_workflow(service_request: ServiceRequest, target_status: str) -> None:
    if target_status != Status.COMPLETED:
        return
    from workflow.models import WorkflowStepInstance
    open_steps = service_request.workflow_steps.exclude(
        status__in=[WorkflowStepInstance.Status.COMPLETED, WorkflowStepInstance.Status.SKIPPED]
    )
    if open_steps.exists():
        open_names = ", ".join(open_steps.values_list("step_template__name", flat=True))
        raise TransitionGuardError(
            f"Cannot mark {service_request.reference_code} Completed: "
            f"open workflow steps remain ({open_names})."
        )


# Ordered registry — every guard runs; each is independent and only acts
# when its own `target_status` condition matches. Add new domain rules
# by appending a function here, not by editing transition_state().
GUARDS = [
    _guard_ready_requires_complete_checklist,
    _guard_completed_requires_closed_workflow,
]


def assert_transition_allowed(service_request: ServiceRequest, target_status: str) -> None:
    current = service_request.status
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition ServiceRequest from '{current}' to '{target_status}'. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
        )
    for guard in GUARDS:
        guard(service_request, target_status)


# Backwards-compatible alias for the graph-only check, kept for any
# external caller that genuinely only wants the edge check (e.g. a UI
# that wants to grey out impossible buttons without running guards that
# hit the DB).
def assert_valid_transition(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition ServiceRequest from '{current}' to '{target}'. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
        )
