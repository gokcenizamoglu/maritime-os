from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from config.base_models import TimeStampedModel


class OperationTemplate(TimeStampedModel):
    """A process variant belonging to one tenant service offering."""

    service_offering = models.ForeignKey(
        "catalog.TenantServiceOffering", on_delete=models.PROTECT,
        related_name="operation_templates",
    )
    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=80)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["service_offering", "code"],
                name="unique_operation_template_code_per_offering",
            ),
            models.UniqueConstraint(
                fields=["service_offering"],
                condition=Q(is_active=True, is_default=True),
                name="one_active_default_template_per_offering",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.service_offering})"


PROTECTED_VERSION_STATUSES = frozenset({"published", "retired", "archived"})


class OperationTemplateVersionQuerySet(models.QuerySet):
    """Keep bulk ORM writes inside the version lifecycle boundary."""

    def _assert_no_protected_rows(self):
        if self.filter(status__in=PROTECTED_VERSION_STATUSES).exists():
            raise ValidationError("Published, retired, and archived versions are immutable.")

    def update(self, **kwargs):
        if kwargs.get("status") in PROTECTED_VERSION_STATUSES:
            raise ValidationError("Version status changes must use the workflow service.")
        self._assert_no_protected_rows()
        return super().update(**kwargs)

    def delete(self):
        self._assert_no_protected_rows()
        return super().delete()

    def bulk_update(self, objs, fields, batch_size=None):
        objs = list(objs)
        self.filter(pk__in=[obj.pk for obj in objs])._assert_no_protected_rows()
        if "status" in fields and any(obj.status in PROTECTED_VERSION_STATUSES for obj in objs):
            raise ValidationError("Version status changes must use the workflow service.")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        objs = list(objs)
        if any(obj.status in PROTECTED_VERSION_STATUSES for obj in objs):
            raise ValidationError("Versions must be created as drafts and published by the workflow service.")
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields,
            unique_fields=unique_fields,
        )


class OperationTemplateVersion(TimeStampedModel):
    """An immutable published process recipe."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"
        ARCHIVED = "archived", "Archived"

    operation_template = models.ForeignKey(
        OperationTemplate, on_delete=models.PROTECT, related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_operation_template_versions",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="published_operation_template_versions",
    )

    class Meta:
        ordering = ["operation_template", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["operation_template", "version_number"],
                name="unique_operation_template_version_number",
            ),
            models.UniqueConstraint(
                fields=["operation_template"],
                condition=Q(status="published"),
                name="one_published_version_per_operation_template",
            ),
        ]

    objects = OperationTemplateVersionQuerySet.as_manager()

    def __str__(self):
        return f"{self.operation_template.code} v{self.version_number} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.pk and self.status in PROTECTED_VERSION_STATUSES:
            raise ValidationError("Versions must be created as drafts and published by the workflow service.")
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            changed = any(
                getattr(previous, field) != getattr(self, field)
                for field in (
                    "operation_template_id", "version_number", "created_at", "created_by_id",
                    "published_at", "published_by_id",
                )
            )
            if previous.status == self.Status.ARCHIVED:
                raise ValidationError("Archived operation template versions are immutable.")
            if previous.status == self.Status.RETIRED and (
                changed or self.status not in {self.Status.RETIRED, self.Status.ARCHIVED}
            ):
                raise ValidationError("Retired operation template versions are immutable except for archiving.")
            if previous.status == self.Status.PUBLISHED and (
                changed or self.status not in {self.Status.PUBLISHED, self.Status.RETIRED, self.Status.ARCHIVED}
            ):
                raise ValidationError("Published operation template versions are immutable except for lifecycle status.")
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in PROTECTED_VERSION_STATUSES:
            raise ValidationError("Published, retired, and archived versions cannot be deleted.")
        return super().delete(*args, **kwargs)


def _assert_version_ids_are_draft(version_ids):
    version_ids = {version_id for version_id in version_ids if version_id}
    if version_ids and OperationTemplateVersion.objects.filter(pk__in=version_ids).exclude(
        status=OperationTemplateVersion.Status.DRAFT,
    ).exists():
        raise ValidationError("Only draft operation template definitions can be changed.")


class VersionedDefinitionQuerySet(models.QuerySet):
    """Apply the draft-only rule to ORM bulk operations as well as save()."""

    def _assert_draft_versions(self, extra_version_ids=()):
        version_ids = set(self.values_list("operation_template_version_id", flat=True))
        version_ids.update(extra_version_ids)
        _assert_version_ids_are_draft(version_ids)

    def update(self, **kwargs):
        extra = [kwargs["operation_template_version_id"]] if "operation_template_version_id" in kwargs else []
        self._assert_draft_versions(extra)
        return super().update(**kwargs)

    def delete(self):
        self._assert_draft_versions()
        return super().delete()

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        objs = list(objs)
        _assert_version_ids_are_draft(
            getattr(obj, "operation_template_version_id", None) for obj in objs
        )
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields,
            unique_fields=unique_fields,
        )

    def bulk_update(self, objs, fields, batch_size=None):
        objs = list(objs)
        extra = (
            getattr(obj, "operation_template_version_id", None)
            for obj in objs
        ) if "operation_template_version" in fields else ()
        self.filter(pk__in=[obj.pk for obj in objs])._assert_draft_versions(extra)
        return super().bulk_update(objs, fields, batch_size=batch_size)


class WorkflowStepDependencyQuerySet(models.QuerySet):
    """Protect the explicit dependency through model, including bulk writes."""

    @staticmethod
    def _assert_edges_are_editable(edges):
        step_ids = {step_id for edge in edges for step_id in edge if step_id}
        steps = list(WorkflowStepTemplate.objects.filter(pk__in=step_ids))
        versions = {step.operation_template_version_id for step in steps if step.operation_template_version_id}
        _assert_version_ids_are_draft(versions)
        by_id = {step.id: step for step in steps}
        for source_id, target_id in edges:
            source = by_id.get(source_id)
            target = by_id.get(target_id)
            if source_id == target_id:
                raise ValidationError("A workflow step cannot depend on itself.")
            if source and target and source.operation_template_version_id and (
                source.operation_template_version_id != target.operation_template_version_id
            ):
                raise ValidationError("Workflow dependencies must stay within one operation template version.")

    def _current_edges(self):
        return list(self.values_list("from_workflowsteptemplate_id", "to_workflowsteptemplate_id"))

    def update(self, **kwargs):
        edges = self._current_edges()
        edges = [
            (
                kwargs.get("from_workflowsteptemplate_id", source_id),
                kwargs.get("to_workflowsteptemplate_id", target_id),
            )
            for source_id, target_id in edges
        ]
        self._assert_edges_are_editable(edges)
        return super().update(**kwargs)

    def delete(self):
        self._assert_edges_are_editable(self._current_edges())
        return super().delete()

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        objs = list(objs)
        edges = [
            (obj.from_workflowsteptemplate_id, obj.to_workflowsteptemplate_id)
            for obj in objs
        ]
        self._assert_edges_are_editable(edges)
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields,
            unique_fields=unique_fields,
        )

    def bulk_update(self, objs, fields, batch_size=None):
        objs = list(objs)
        edges = self.filter(pk__in=[obj.pk for obj in objs])._current_edges() if not {"from_workflowsteptemplate", "to_workflowsteptemplate"}.intersection(fields) else [
            (obj.from_workflowsteptemplate_id, obj.to_workflowsteptemplate_id) for obj in objs
        ]
        self._assert_edges_are_editable(edges)
        return super().bulk_update(objs, fields, batch_size=batch_size)


class WorkflowStepTemplate(models.Model):
    """
    A configurable step definition for an OperationTemplateVersion.

    Parallelism is modeled via `depends_on` (self-referential M2M), NOT
    via a linear `order` integer. A step with no dependencies, or whose
    dependencies are already satisfied, is eligible to start immediately
    — this is how "Minimum Safe Manning" and "waiting for P&I Blue Card"
    can run at the same time after "Registry issued" completes, per the
    real workflow example (Documents -> Lawyer review -> Registry issued
    -> [Radio license, Minimum Safe Manning, P&I Blue Card] in parallel
    -> ... -> CSR issued).

    The nullable service_type/flag fields remain as a legacy compatibility
    path for pre-versioned rows. New runtime selection always uses the
    version foreign key; published definitions are immutable.
    """
    operation_template_version = models.ForeignKey(
        OperationTemplateVersion, on_delete=models.PROTECT,
        related_name="workflow_step_templates", null=True, blank=True,
    )
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.CASCADE, related_name="workflow_step_templates",
        null=True, blank=True,
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
        through="WorkflowStepDependency",
        through_fields=("from_workflowsteptemplate", "to_workflowsteptemplate"),
        help_text="Steps that must be COMPLETED before this step becomes eligible to start.",
    )

    objects = VersionedDefinitionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service_type", "flag", "code"], name="unique_step_code_per_service_flag"),
            models.UniqueConstraint(
                fields=["operation_template_version", "code"],
                condition=Q(operation_template_version__isnull=False),
                name="unique_step_code_per_operation_version",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.operation_template_version or self.service_type})"

    def save(self, *args, **kwargs):
        if self.operation_template_version_id:
            version = OperationTemplateVersion.objects.get(pk=self.operation_template_version_id)
            if version.status != OperationTemplateVersion.Status.DRAFT:
                raise ValidationError("Only draft workflow definitions can be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if (
            self.operation_template_version_id
            and OperationTemplateVersion.objects.get(pk=self.operation_template_version_id).status
            != OperationTemplateVersion.Status.DRAFT
        ):
            raise ValidationError("Only draft workflow definitions can be deleted.")
        return super().delete(*args, **kwargs)


class WorkflowStepDependency(models.Model):
    from_workflowsteptemplate = models.ForeignKey(
        WorkflowStepTemplate, on_delete=models.CASCADE, related_name="dependency_edges",
    )
    to_workflowsteptemplate = models.ForeignKey(
        WorkflowStepTemplate, on_delete=models.CASCADE, related_name="dependent_edges",
    )

    objects = WorkflowStepDependencyQuerySet.as_manager()

    class Meta:
        db_table = "workflow_workflowsteptemplate_depends_on"
        constraints = [
            models.UniqueConstraint(
                fields=["from_workflowsteptemplate", "to_workflowsteptemplate"],
                name="unique_workflow_step_dependency",
            ),
        ]

    def _assert_editable(self):
        WorkflowStepDependencyQuerySet._assert_edges_are_editable([
            (self.from_workflowsteptemplate_id, self.to_workflowsteptemplate_id),
        ])

    def save(self, *args, **kwargs):
        self._assert_editable()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._assert_editable()
        return super().delete(*args, **kwargs)


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


from django.db.models.signals import m2m_changed
from django.dispatch import receiver


@receiver(m2m_changed, sender=WorkflowStepTemplate.depends_on.through)
def _guard_published_workflow_dependencies(sender, instance, action, **kwargs):
    if action in {"pre_add", "pre_remove", "pre_clear"} and instance.operation_template_version_id:
        version = OperationTemplateVersion.objects.get(pk=instance.operation_template_version_id)
        if version.status != OperationTemplateVersion.Status.DRAFT:
            raise ValidationError("Published workflow dependencies are immutable.")
