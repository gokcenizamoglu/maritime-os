from django.db import models


class WorkflowStepTemplate(models.Model):
    """
    A configurable step definition for a ServiceType (+ optionally a
    specific Flag, since e.g. Panama Owner Change has different steps
    than Palau Owner Change).

    Parallelism is modeled via `depends_on` (self-referential M2M), NOT
    via a linear `order` integer. A step with no dependencies, or whose
    dependencies are already satisfied, is eligible to start immediately
    — this is how "Minimum Safe Manning" and "waiting for P&I Blue Card"
    can run at the same time after "Registry issued" completes, per the
    real workflow example (Documents -> Lawyer review -> Registry issued
    -> [Radio license, Minimum Safe Manning, P&I Blue Card] in parallel
    -> ... -> CSR issued).

    NOT implemented in Phase 1 (WorkflowStepInstance is created and
    tracked, but auto-advancement/automation is Phase 2). This table
    exists now specifically so the Phase 2 automation engine has a graph
    to walk instead of needing a data model migration first.
    """
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.CASCADE, related_name="workflow_step_templates",
    )
    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.CASCADE, related_name="workflow_step_templates",
        null=True, blank=True,
        help_text="Null = applies to this ServiceType regardless of flag.",
    )
    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=150)
    is_external = models.BooleanField(
        default=False,
        help_text="True if this step's completion depends on an external "
                   "organization's response (lawyer, flag authority, P&I club).",
    )
    responsible_organization_type = models.ForeignKey(
        "catalog.OrganizationType", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="workflow_step_templates",
    )
    depends_on = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="dependents",
        help_text="Steps that must be COMPLETED before this step becomes eligible to start.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service_type", "flag", "code"], name="unique_step_code_per_service_flag")
        ]

    def __str__(self):
        return f"{self.name} ({self.service_type})"


class WorkflowStepInstance(models.Model):
    """A concrete step instance tracked against one ServiceRequest."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        BLOCKED = "blocked", "Blocked"
        WAITING_EXTERNAL = "waiting_external", "Waiting External"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE, related_name="workflow_steps",
    )
    step_template = models.ForeignKey(
        WorkflowStepTemplate, on_delete=models.PROTECT, related_name="instances",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    assigned_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_workflow_steps",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service_request", "step_template"], name="unique_step_instance_per_request"
            )
        ]

    def __str__(self):
        return f"{self.step_template.name} [{self.status}] on {self.service_request}"
