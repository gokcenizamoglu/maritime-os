from config.base_models import TenantScopedModel
from django.conf import settings
from django.db import models


class ActivityLog(TenantScopedModel):
    """
    Append-only event log. Every meaningful action in the system writes
    one row here: document uploaded, classification changed, checklist
    item completed, workflow step completed, external response received,
    state transition.

    Deliberately generic (verb + entity_type + entity_id + metadata JSON)
    rather than one FK per possible entity type. A rigid schema here
    would need a migration every time a new event type is added; this
    one doesn't. The trade-off — you lose DB-level FK integrity on the
    logged entity — is acceptable for an audit trail whose job is to be
    an immutable historical record, not a queryable relation.

    This table is also the natural backing store for a future customer-
    or ops-facing "timeline" view, and for Phase 2's audit log /
    compliance requirements — no new model needed, just new consumers
    of this one.
    """
    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE,
        related_name="activity_log", null=True, blank=True,
    )
    actor_type = models.CharField(
        max_length=20,
        choices=[("user", "Internal User"), ("customer", "Customer"), ("system", "System")],
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_log_entries",
    )
    verb = models.CharField(
        max_length=100,
        help_text="e.g. 'document.uploaded', 'document.classified', "
                   "'checklist_item.completed', 'service_request.status_changed'",
    )
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["service_request", "-created_at"])]

    def __str__(self):
        return f"{self.verb} on {self.entity_type}:{self.entity_id}"
