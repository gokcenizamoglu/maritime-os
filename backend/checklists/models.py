from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from workflow.models import OperationTemplateVersion


class VersionedChecklistDefinitionQuerySet(models.QuerySet):
    """Apply the draft-only rule to all checklist definition write paths."""

    def _assert_draft_versions(self, extra_version_ids=()):
        version_ids = set(self.values_list("operation_template_version_id", flat=True))
        version_ids.update(extra_version_ids)
        version_ids.discard(None)
        if version_ids and OperationTemplateVersion.objects.filter(pk__in=version_ids).exclude(
            status=OperationTemplateVersion.Status.DRAFT,
        ).exists():
            raise ValidationError("Only draft operation template definitions can be changed.")

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
        self._assert_draft_versions(
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


class ChecklistTemplate(models.Model):
    """
    A versioned document requirement: "this OperationTemplateVersion
    requires DocumentType Z (min_count times)."

    This is deliberately a separate table from ChecklistItem. Collapsing
    the two — i.e. hardcoding requirements directly onto ServiceRequest —
    is the single decision most likely to make "dynamic, configurable,
    admin-editable checklists" impossible to retrofit later. Templates
    are platform/tenant configuration; Items are per-case instances of
    that configuration.

    ``operation_template_version`` is the runtime source of truth. The
    nullable service_type/flag fields remain only for legacy global rows
    during the staged migration and are not used for new ServiceRequests.
    """
    operation_template_version = models.ForeignKey(
        OperationTemplateVersion, on_delete=models.PROTECT,
        related_name="checklist_templates", null=True, blank=True,
    )
    code = models.SlugField(max_length=80, blank=True)
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.CASCADE, related_name="checklist_templates",
        null=True, blank=True,
    )
    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.CASCADE, related_name="checklist_templates",
        null=True, blank=True,
    )
    document_type = models.ForeignKey(
        "catalog.DocumentType", on_delete=models.PROTECT, related_name="checklist_templates",
    )
    min_count = models.PositiveIntegerField(
        default=1,
        help_text="How many documents of this type are required (e.g. "
                   "passport copies for each crew member could be >1).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service_type", "flag", "document_type"],
                name="unique_checklist_rule_per_service_flag_doctype",
            ),
            models.UniqueConstraint(
                fields=["operation_template_version", "code"],
                condition=Q(operation_template_version__isnull=False),
                name="unique_checklist_code_per_operation_version",
            ),
            models.UniqueConstraint(
                fields=["operation_template_version", "document_type"],
                condition=Q(operation_template_version__isnull=False),
                name="unique_checklist_doctype_per_operation_version",
            ),
        ]

    objects = VersionedChecklistDefinitionQuerySet.as_manager()

    def __str__(self):
        return f"{self.operation_template_version or self.service_type} requires {self.document_type}"

    def save(self, *args, **kwargs):
        if self.operation_template_version_id:
            version = OperationTemplateVersion.objects.get(pk=self.operation_template_version_id)
            if version.status != OperationTemplateVersion.Status.DRAFT:
                raise ValidationError("Only draft checklist definitions can be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if (
            self.operation_template_version_id
            and OperationTemplateVersion.objects.get(pk=self.operation_template_version_id).status
            != OperationTemplateVersion.Status.DRAFT
        ):
            raise ValidationError("Only draft checklist definitions can be deleted.")
        return super().delete(*args, **kwargs)


class ChecklistItem(models.Model):
    """
    A single required-document line item, INSTANTIATED onto a specific
    ServiceRequest from the matching ChecklistTemplates at creation time.

    `is_complete` is a CACHE, not a source of truth. The real answer to
    "is this item complete" is always: does this ServiceRequest have at
    least `required_count` Documents mapped to `document_type` with
    status >= classified? The cached field exists purely so list views
    don't have to recompute a join on every page load — it must only
    ever be written by checklists.services.recompute_checklist_item(),
    never set directly from a view or admin action.
    """
    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE, related_name="checklist_items",
    )
    document_type = models.ForeignKey(
        "catalog.DocumentType", on_delete=models.PROTECT, related_name="checklist_items",
    )
    source_template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.SET_NULL, related_name="instances",
        null=True, blank=True,
    )
    required_count = models.PositiveIntegerField(default=1)
    is_complete = models.BooleanField(
        default=False,
        help_text="DERIVED cache — see recompute_checklist_item(). Do not set directly.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service_request", "document_type"],
                name="unique_checklist_item_per_request_and_doctype",
            )
        ]
        ordering = ["document_type__name"]

    def __str__(self):
        return f"{self.document_type} for {self.service_request}"
