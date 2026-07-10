from django.db import models


class ChecklistTemplate(models.Model):
    """
    The CONFIGURABLE rule: "for ServiceType X + Flag Y, DocumentType Z
    is required (min_count times)."

    This is deliberately a separate table from ChecklistItem. Collapsing
    the two — i.e. hardcoding requirements directly onto ServiceRequest —
    is the single decision most likely to make "dynamic, configurable,
    admin-editable checklists" impossible to retrofit later. Templates
    are platform/tenant configuration; Items are per-case instances of
    that configuration.

    Not tenant-scoped by default: the maritime document requirements for
    "Owner Change + Panama" are a matter of Panamanian regulation, not
    tenant preference. If a specific tenant needs to add an extra
    internal requirement on top, that's a Phase 2 tenant-override table,
    not a fork of this one.
    """
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.CASCADE, related_name="checklist_templates",
    )
    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.CASCADE, related_name="checklist_templates",
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
            )
        ]

    def __str__(self):
        return f"{self.service_type} + {self.flag} requires {self.document_type}"


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
