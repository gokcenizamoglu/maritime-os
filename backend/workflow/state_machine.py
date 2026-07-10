"""
Transition graph for WorkflowStepInstance.status.

Deliberately mirrors `service_requests.state_machine`'s shape (a plain
ALLOWED_TRANSITIONS dict + an assert function) rather than inventing a
different pattern for the second state machine in the codebase —
consistency here means a future engineer only has to learn this
approach once.

BLOCKED is reachable only via the orchestration layer
(`workflow.services.sync_step_statuses`), never via a direct
human-initiated `update_step_status` call — hence it's absent as a
TARGET in this graph but present as a valid FROM state (the
orchestration layer bypasses this check entirely by writing `.status`
directly, which is correct: it's not a human decision being validated,
it's a computed consequence of dependency state).
"""
from workflow.models import WorkflowStepInstance

Status = WorkflowStepInstance.Status

ALLOWED_TRANSITIONS = {
    Status.PENDING: {Status.ACTIVE, Status.SKIPPED},
    Status.BLOCKED: {Status.SKIPPED},  # can skip a blocked step (e.g. N/A for this case), but not start it
    Status.ACTIVE: {Status.WAITING_EXTERNAL, Status.COMPLETED, Status.SKIPPED},
    Status.WAITING_EXTERNAL: {Status.ACTIVE, Status.COMPLETED},
    Status.COMPLETED: set(),
    Status.SKIPPED: set(),
}


class InvalidStepTransitionError(Exception):
    pass


def assert_step_transition_allowed(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStepTransitionError(
            f"Cannot transition WorkflowStepInstance from '{current}' to '{target}'. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
        )
