"""
Reference/catalog data: the "vocabulary" of the domain.

These are deliberately platform-global (NOT tenant-scoped) because
"Passport", "STCW", "Panama", "Owner Change" mean the same thing to every
maritime consultancy on the platform. Duplicating them per-tenant would
mean every new tenant has to re-enter the entire maritime document/flag
taxonomy from scratch, and cross-tenant analytics ("how many Owner
Changes did the platform process this month") become a JOIN nightmare.

If a tenant genuinely needs a custom document type later, that's a
deliberate Phase 2 feature (tenant-level overrides/extensions), not the
Phase 1 default.
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from config.base_models import TenantScopedModel


class Flag(models.Model):
    """A flag state / registry (Panama, Palau, Marshall Islands, ...)."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)  # e.g. "PA", "PW"
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServiceType(models.Model):
    """A category of service the consultancy performs."""

    class FlagScope(models.TextChoices):
        REQUIRED = "required", "Flag required"
        OPTIONAL = "optional", "Flag optional"
        NOT_APPLICABLE = "not_applicable", "Flag not applicable"

    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    flag_scope = models.CharField(
        max_length=20,
        choices=FlagScope.choices,
        default=FlagScope.REQUIRED,
        help_text="Whether this service is offered within a flag context.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DocumentType(models.Model):
    """
    A kind of document (Passport, STCW, Bill of Sale, ...).

    is_global distinguishes platform-wide standard types from a future
    tenant-specific extension (Phase 2). Keeping the flag here now costs
    nothing and avoids a schema migration later just to add it.
    """
    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_global = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OrganizationType(models.Model):
    """Classifies an Organization's role capability: law firm, flag authority, P&I club, class society..."""
    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class TenantServiceOffering(TenantScopedModel):
    """A tenant's commercial/operational ability to accept a service.

    This is intentionally separate from OperationTemplate: an offering may
    exist before a process recipe is configured, and may have multiple
    process variants. ``flag`` is a denormalized catalog reference used for
    reporting/filtering; when ``flag_relationship`` is present it must point
    to the same flag and is the source of the tenant's relationship validity.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.PROTECT, related_name="tenant_offerings",
    )
    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.PROTECT, related_name="tenant_offerings",
        null=True, blank=True,
    )
    flag_relationship = models.ForeignKey(
        "organizations.TenantFlagRelationship", on_delete=models.PROTECT,
        related_name="service_offerings", null=True, blank=True,
    )
    display_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INACTIVE)
    accepts_new_requests = models.BooleanField(default=False)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["service_type__name", "flag__name", "display_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "service_type"],
                condition=Q(flag__isnull=True, flag_relationship__isnull=True),
                name="unique_unflagged_offering_per_tenant_service",
            ),
            models.UniqueConstraint(
                fields=["tenant", "service_type", "flag_relationship"],
                condition=Q(flag_relationship__isnull=False),
                name="unique_offering_per_tenant_service_relationship",
            ),
        ]

    def __str__(self):
        return self.display_name or f"{self.service_type} ({self.flag or 'unflagged'})"

    def clean(self):
        super().clean()
        errors = {}
        if self.flag_relationship_id:
            relationship = self.flag_relationship
            if self.tenant_id and relationship.tenant_id != self.tenant_id:
                errors["flag_relationship"] = (
                    "The flag relationship must belong to the offering tenant."
                )
            if self.flag_id and relationship.flag_id != self.flag_id:
                errors["flag_relationship"] = (
                    "The flag relationship must reference the offering flag."
                )
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            identity_changed = any(
                getattr(original, field) != getattr(self, field)
                for field in (
                    "tenant_id", "service_type_id", "flag_id", "flag_relationship_id",
                )
            )
            if identity_changed:
                from workflow.models import PROTECTED_VERSION_STATUSES

                identity_is_locked = (
                    self.service_requests.exists()
                    or self.operation_templates.filter(
                        versions__status__in=PROTECTED_VERSION_STATUSES,
                    ).exists()
                )
            else:
                identity_is_locked = False
            if identity_is_locked:
                errors["service_type"] = (
                    "An offering referenced by service requests or protected template "
                    "versions cannot change its identity."
                )
            if (
                original.tenant_id != self.tenant_id
                and self.operation_templates.exists()
            ):
                errors["tenant"] = (
                    "An offering with operation templates cannot move to another tenant."
                )
        if errors:
            raise ValidationError(errors)

    def is_available_for_new_requests(self, *, today=None) -> bool:
        today = today or timezone.localdate()
        return (
            self.status == self.Status.ACTIVE
            and self.accepts_new_requests
            and (self.valid_from is None or self.valid_from <= today)
            and (self.valid_until is None or self.valid_until >= today)
            and (
                self.flag_relationship_id is None
                or self.flag_relationship.is_available_for_new_requests(today=today)
            )
        )
