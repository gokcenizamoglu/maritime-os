"""
Service layer for the workflow domain — the orchestration layer.

ARCHITECTURAL CHANGE (from "passive tracking" to "orchestration"):
Previously a WorkflowStepInstance just sat in whatever status someone
set it to; "is this step actually startable yet" was a read-only query
(`get_eligible_steps`) that nothing acted on. Now the lifecycle is
explicit and self-maintaining:

    PENDING  — dependencies satisfied, waiting for someone/something to start it
    BLOCKED  — dependencies NOT satisfied yet; cannot be started
    ACTIVE   — being worked on
    WAITING_EXTERNAL — handed off to an external organization, out of our hands
    COMPLETED / SKIPPED — terminal

`sync_step_statuses()` is the orchestration function: given the current
completion state of all of a ServiceRequest's steps, it moves steps
between PENDING and BLOCKED automatically. This is what makes parallel
steps (Radio License / Minimum Safe Manning / P&I Blue Card all
unlocking simultaneously once Registry Issued completes) a property of
the DATA rather than something a human has to notice and act on. It's
still entirely synchronous/manually-triggered in Phase 1 (called after
`update_step_status` completes a step) — Phase 2's automation engine is
"call this function on a timer/webhook too", not a different function.
"""
from django.db import transaction
from django.utils import timezone
from events.dispatcher import emit
from events.types import WORKFLOW_STEP_STATUS_CHANGED
from service_requests.models import ServiceRequest
from workflow.models import WorkflowStepInstance, WorkflowStepTemplate
from workflow.state_machine import assert_step_transition_allowed

Status = WorkflowStepInstance.Status


def generate_workflow_steps_for_service_request(service_request: ServiceRequest) -> list[WorkflowStepInstance]:
    """
    Instantiate step instances from templates matching this request's
    service_type, preferring flag-specific templates over flag-agnostic
    ones (deduplicated by `code` — see WorkflowStepTemplate docstring for
    why two template ROWS can share a code and why that must be
    resolved BEFORE instantiation, not after).

    Every step starts life as BLOCKED unless it has no dependencies, in
    which case it starts PENDING (immediately startable) — this is the
    orchestration layer's first job, done at creation time via
    `sync_step_statuses` right after instantiation.
    """
    candidates = WorkflowStepTemplate.objects.filter(
        service_type=service_request.service_type,
    ).filter(_flag_matches(service_request.flag))

    templates_by_code: dict[str, WorkflowStepTemplate] = {}
    for template in candidates:
        existing = templates_by_code.get(template.code)
        is_more_specific = existing is None or (existing.flag_id is None and template.flag_id is not None)
        if is_more_specific:
            templates_by_code[template.code] = template

    instances = []
    with transaction.atomic():
        for template in templates_by_code.values():
            instance, _ = WorkflowStepInstance.objects.get_or_create(
                service_request=service_request, step_template=template,
                defaults={"status": Status.BLOCKED},
            )
            instances.append(instance)
        sync_step_statuses(service_request)
    return instances


def _flag_matches(flag):
    from django.db.models import Q
    return Q(flag=flag) | Q(flag__isnull=True)


def _dependencies_satisfied(instance: WorkflowStepInstance, service_request: ServiceRequest) -> bool:
    dep_codes = set(instance.step_template.depends_on.values_list("code", flat=True))
    if not dep_codes:
        return True
    satisfied_codes = set(
        service_request.workflow_steps.filter(
            status__in=[Status.COMPLETED, Status.SKIPPED],
            step_template__code__in=dep_codes,
        ).values_list("step_template__code", flat=True)
    )
    return dep_codes.issubset(satisfied_codes)


def sync_step_statuses(service_request: ServiceRequest) -> list[WorkflowStepInstance]:
    """
    THE orchestration function. Walks every non-terminal step on this
    ServiceRequest and moves BLOCKED -> PENDING (dependencies now met) or
    PENDING -> BLOCKED (shouldn't normally happen going backwards, but
    kept symmetric in case a completed dependency is ever reverted).
    Never touches ACTIVE, WAITING_EXTERNAL, COMPLETED, or SKIPPED steps
    — those are driven by explicit human/external action via
    `update_step_status`, not by dependency bookkeeping.

    Call this after ANY step reaches COMPLETED or SKIPPED — see
    `update_step_status`, which calls it automatically.
    """
    changed = []
    for instance in service_request.workflow_steps.filter(status__in=[Status.PENDING, Status.BLOCKED]):
        satisfied = _dependencies_satisfied(instance, service_request)
        target = Status.PENDING if satisfied else Status.BLOCKED
        if instance.status != target:
            instance.status = target
            instance.save(update_fields=["status"])
            changed.append(instance)
    return changed


def get_eligible_steps(service_request: ServiceRequest) -> list[WorkflowStepInstance]:
    """Steps currently startable right now — i.e. status == PENDING.
    Kept as a thin, explicit query (rather than recomputing dependency
    logic here) now that PENDING vs BLOCKED is maintained continuously
    by `sync_step_statuses` instead of computed on read."""
    return list(service_request.workflow_steps.filter(status=Status.PENDING))


@transaction.atomic
def update_step_status(*, step_instance: WorkflowStepInstance, status: str, actor_user) -> WorkflowStepInstance:
    """
    The ONLY sanctioned way to change a WorkflowStepInstance's status.
    Validates against `workflow.state_machine` first, then — if the step
    just reached a terminal state (COMPLETED/SKIPPED) — runs
    `sync_step_statuses` so any dependent steps that just became
    eligible flip from BLOCKED to PENDING in the same transaction.
    """
    assert_step_transition_allowed(step_instance.status, status)
    previous_status = step_instance.status
    step_instance.status = status
    if status == Status.ACTIVE and not step_instance.started_at:
        step_instance.started_at = timezone.now()
    if status == Status.COMPLETED:
        step_instance.completed_at = timezone.now()
    step_instance.save()

    if status in (Status.COMPLETED, Status.SKIPPED):
        sync_step_statuses(step_instance.service_request)

    emit(
        WORKFLOW_STEP_STATUS_CHANGED,
        step_instance=step_instance,
        previous_status=previous_status,
        new_status=status,
        actor_user=actor_user,
    )
    return step_instance
