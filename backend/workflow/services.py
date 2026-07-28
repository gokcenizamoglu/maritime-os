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
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from events.dispatcher import emit
from events.types import WORKFLOW_STEP_STATUS_CHANGED
from service_requests.models import ServiceRequest
from workflow.models import OperationTemplate, OperationTemplateVersion, WorkflowStepInstance, WorkflowStepTemplate
from workflow.state_machine import assert_step_transition_allowed

Status = WorkflowStepInstance.Status


class OperationTemplateValidationError(ValueError):
    pass


def _validate_template_tenant(*, tenant, operation_template: OperationTemplate):
    if operation_template.service_offering.tenant_id != tenant.id:
        raise OperationTemplateValidationError("Operation template does not belong to the acting tenant.")


@transaction.atomic
def save_operation_template(*, tenant, data, instance=None) -> OperationTemplate:
    offering = data.get("service_offering", instance.service_offering if instance else None)
    if offering is None or offering.tenant_id != tenant.id:
        raise OperationTemplateValidationError("Operation template offering does not belong to the acting tenant.")
    make_default = data.get("is_default", False)
    if instance is None:
        data = dict(data)
        data["is_default"] = False
        template = OperationTemplate.objects.create(**data)
        if make_default:
            return set_default_template(tenant=tenant, operation_template=template)
        return template
    if instance.service_offering_id != offering.id and instance.versions.exists():
        raise OperationTemplateValidationError("A template with versions cannot move to another offering.")
    make_default = data.get("is_default", instance.is_default)
    data = dict(data)
    if make_default:
        data["is_default"] = False
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    if make_default:
        return set_default_template(tenant=tenant, operation_template=instance)
    return instance


def _validate_version_graph(version: OperationTemplateVersion) -> None:
    steps = list(version.workflow_step_templates.all().prefetch_related("depends_on"))
    codes = [step.code for step in steps]
    if any(not code for code in codes) or len(codes) != len(set(codes)):
        raise OperationTemplateValidationError("Workflow step codes must be unique within a version.")
    step_by_id = {step.id: step for step in steps}
    graph = {step.id: set() for step in steps}
    for step in steps:
        for dependency in step.depends_on.all():
            if dependency.operation_template_version_id != version.id or dependency.id not in step_by_id:
                raise OperationTemplateValidationError(
                    "Workflow dependencies must stay within the same operation template version."
                )
            graph[step.id].add(dependency.id)

    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            raise OperationTemplateValidationError("Workflow dependency graph contains a cycle.")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)

    checklist_codes = list(
        version.checklist_templates.filter(is_active=True).values_list("code", flat=True)
    )
    if any(not code for code in checklist_codes) or len(checklist_codes) != len(set(checklist_codes)):
        raise OperationTemplateValidationError("Checklist item codes must be unique within a version.")


@transaction.atomic
def create_draft_version(*, tenant, operation_template: OperationTemplate, created_by=None) -> OperationTemplateVersion:
    _validate_template_tenant(tenant=tenant, operation_template=operation_template)
    next_number = (
        OperationTemplateVersion.objects
        .filter(operation_template=operation_template)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first() or 0
    ) + 1
    return OperationTemplateVersion.objects.create(
        operation_template=operation_template,
        version_number=next_number,
        created_by=created_by,
    )


@transaction.atomic
def clone_published_version(*, tenant, source_version: OperationTemplateVersion, created_by=None) -> OperationTemplateVersion:
    source_version = (
        OperationTemplateVersion.objects
        .select_related("operation_template__service_offering")
        .get(pk=source_version.pk)
    )
    _validate_template_tenant(tenant=tenant, operation_template=source_version.operation_template)
    if source_version.status != OperationTemplateVersion.Status.PUBLISHED:
        raise OperationTemplateValidationError("Only a published version can be cloned.")
    target = create_draft_version(
        tenant=tenant, operation_template=source_version.operation_template, created_by=created_by,
    )
    from checklists.models import ChecklistTemplate
    for definition in source_version.checklist_templates.all():
        ChecklistTemplate.objects.create(
            operation_template_version=target,
            code=definition.code,
            document_type=definition.document_type,
            min_count=definition.min_count,
            is_active=definition.is_active,
        )

    source_steps = list(source_version.workflow_step_templates.all())
    step_map = {}
    for source in source_steps:
        step_map[source.id] = WorkflowStepTemplate.objects.create(
            operation_template_version=target,
            code=source.code,
            name=source.name,
            is_external=source.is_external,
            responsible_organization_type=source.responsible_organization_type,
        )
    for source in source_steps:
        step_map[source.id].depends_on.set(
            [step_map[dependency.id] for dependency in source.depends_on.all()]
        )
    return target


@transaction.atomic
def publish_version(*, tenant, version: OperationTemplateVersion, published_by=None) -> OperationTemplateVersion:
    version = (
        OperationTemplateVersion.objects
        .select_related("operation_template__service_offering")
        .get(pk=version.pk)
    )
    _validate_template_tenant(tenant=tenant, operation_template=version.operation_template)
    if version.status != OperationTemplateVersion.Status.DRAFT:
        raise OperationTemplateValidationError("Only draft versions can be published.")
    _validate_version_graph(version)
    previous_versions = OperationTemplateVersion.objects.filter(
        operation_template=version.operation_template,
        status=OperationTemplateVersion.Status.PUBLISHED,
    )
    for previous in previous_versions:
        previous.status = OperationTemplateVersion.Status.RETIRED
        previous.save(update_fields=["status", "updated_at"])
    version.status = OperationTemplateVersion.Status.PUBLISHED
    version.published_by = published_by
    version.published_at = timezone.now()
    try:
        version.save()
    except ValidationError as exc:
        raise OperationTemplateValidationError(str(exc)) from exc
    return version


@transaction.atomic
def retire_version(*, tenant, version: OperationTemplateVersion) -> OperationTemplateVersion:
    version = (
        OperationTemplateVersion.objects
        .select_related("operation_template__service_offering")
        .get(pk=version.pk)
    )
    _validate_template_tenant(tenant=tenant, operation_template=version.operation_template)
    if version.status not in {OperationTemplateVersion.Status.PUBLISHED, OperationTemplateVersion.Status.DRAFT}:
        raise OperationTemplateValidationError("Version is already retired or archived.")
    version.status = OperationTemplateVersion.Status.RETIRED
    version.save(update_fields=["status", "updated_at"])
    return version


@transaction.atomic
def archive_version(*, tenant, version: OperationTemplateVersion) -> OperationTemplateVersion:
    version = (
        OperationTemplateVersion.objects
        .select_related("operation_template__service_offering")
        .get(pk=version.pk)
    )
    _validate_template_tenant(tenant=tenant, operation_template=version.operation_template)
    if version.status != OperationTemplateVersion.Status.RETIRED:
        raise OperationTemplateValidationError("Only retired versions can be archived.")
    version.status = OperationTemplateVersion.Status.ARCHIVED
    version.save(update_fields=["status", "updated_at"])
    return version


@transaction.atomic
def set_default_template(*, tenant, operation_template: OperationTemplate) -> OperationTemplate:
    _validate_template_tenant(tenant=tenant, operation_template=operation_template)
    if not operation_template.is_active:
        raise OperationTemplateValidationError("Only active templates can be made default.")
    OperationTemplate.objects.filter(
        service_offering=operation_template.service_offering,
    ).exclude(pk=operation_template.pk).update(is_default=False)
    operation_template.is_default = True
    operation_template.save(update_fields=["is_default", "updated_at"])
    return operation_template


@transaction.atomic
def save_workflow_definition(*, tenant, data, dependency_codes=None, instance=None):
    version = data.get(
        "operation_template_version", instance.operation_template_version if instance else None,
    )
    if version is None:
        raise OperationTemplateValidationError("operation_template_version is required.")
    if version.operation_template.service_offering.tenant_id != tenant.id:
        raise OperationTemplateValidationError("Version does not belong to the acting tenant.")
    if version.status != OperationTemplateVersion.Status.DRAFT:
        raise OperationTemplateValidationError("Only draft versions can be edited.")
    if instance is None:
        instance = WorkflowStepTemplate.objects.create(**data)
    else:
        if instance.operation_template_version_id != version.id:
            raise OperationTemplateValidationError("A workflow definition cannot move between versions.")
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()

    if dependency_codes is not None:
        dependency_codes = list(dict.fromkeys(dependency_codes))
        dependencies = list(
            WorkflowStepTemplate.objects.filter(
                operation_template_version=version, code__in=dependency_codes,
            )
        )
        if len(dependencies) != len(dependency_codes) or instance.code in dependency_codes:
            raise OperationTemplateValidationError(
                "Dependencies must reference distinct steps in the same version."
            )
        instance.depends_on.set(dependencies)
        _validate_version_graph(version)
    return instance


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
    if service_request.operation_template_version_id:
        candidates = WorkflowStepTemplate.objects.filter(
            operation_template_version_id=service_request.operation_template_version_id,
        ).prefetch_related("depends_on")
        templates_by_code = {template.code: template for template in candidates}
    else:
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
