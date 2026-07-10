from config.base_models import TenantScopedModel
from django.conf import settings
from django.db import models


class ServiceRequest(TenantScopedModel):
    """
    The core entity of the entire system. Everything else — documents,
    checklists, workflow steps, organization involvement, activity —
    hangs off a ServiceRequest.

    Cardinality (deliberate, per domain rules):
      - belongs to exactly ONE Vessel (FK, not M2M)
      - belongs to exactly ONE Customer
      - has exactly ONE ServiceType and ONE Flag
      - a Vessel may have MANY open ServiceRequests concurrently — this
        model enforces nothing that would prevent that (no uniqueness
        constraint on vessel, no "is this vessel busy" check).

    status is a state machine, not a free-text field — see
    service_requests.state_machine for the transition graph. Never set
    `.status = X; .save()` directly outside of
    service_requests.services.transition_state(); that function is the
    only place invariants (valid transitions, side effects like workflow
    step activation) are enforced.
    """
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COLLECTING_DOCUMENTS = "collecting_documents", "Collecting Documents"
        READY = "ready", "Ready"
        IN_PROGRESS = "in_progress", "In Progress"
        WAITING_EXTERNAL = "waiting_external", "Waiting External"
        COMPLETED = "completed", "Completed"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="service_requests",
    )
    vessel = models.ForeignKey(
        "vessels.Vessel", on_delete=models.PROTECT, related_name="service_requests",
    )
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.PROTECT, related_name="service_requests",
    )
    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.PROTECT, related_name="service_requests",
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_service_requests",
    )
    reference_code = models.CharField(
        max_length=50, unique=True,
        help_text="Human-facing case reference, e.g. LM-2026-0417.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["vessel"]),
        ]

    def __str__(self):
        return f"{self.reference_code}: {self.service_type} / {self.flag} ({self.vessel})"


class ServiceRequestSequence(models.Model):
    """
    Backing store for race-safe reference_code generation.

    REVIEW FIX: the original implementation computed the next number as
    `ServiceRequest.objects.filter(...).count() + 1`. Under concurrent
    requests this is a classic read-then-write race — two transactions
    can both read count=41 and both produce "LM-2026-0042", violating
    the unique constraint on reference_code (or worse, silently
    succeeding if that constraint were ever relaxed).

    Fix: one row per (tenant, year), incremented by a SINGLE atomic
    `INSERT ... ON CONFLICT (tenant_id, year) DO UPDATE SET last_number =
    last_number + 1 RETURNING last_number` in
    `services._next_reference_code()`. Because the increment is one
    database statement, there is no read-then-write window in application
    code at all, and the number is never computed in Python — the DB
    both bootstraps the row (INSERT branch) and increments it (DO UPDATE
    branch) atomically, serialized by the unique index below. Concurrent
    creates for DIFFERENT tenants or years never contend — the conflict
    is per-row, not table-wide. (This replaced an earlier
    `select_for_update()` + Python `+= 1` approach, whose first-of-year
    path leaned implicitly on get_or_create's IntegrityError recovery.)

    The UniqueConstraint is not decorative: it is the index the ON
    CONFLICT clause targets AND the last-line guarantee that no two rows
    for one (tenant, year) can exist. Do not remove it.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="service_request_sequences")
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "year"], name="unique_sequence_per_tenant_year"),
        ]
