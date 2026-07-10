from config.base_models import TenantScopedModel
from django.db import models


class Organization(TenantScopedModel):
    """
    An external party: a law firm, a flag authority, a P&I club, a
    classification society. Tenant-scoped because each consultancy
    maintains its own relationships/contacts, even though the same
    real-world flag authority might be represented per-tenant.
    """
    organization_type = models.ForeignKey(
        "catalog.OrganizationType", on_delete=models.PROTECT, related_name="organizations",
    )
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServiceRequestOrganization(TenantScopedModel):
    """
    Join table: which organizations are participating in a given
    ServiceRequest, and in what role.

    This MUST be a many-to-many-with-attributes table, not a single FK
    on ServiceRequest — a real case routinely has a lawyer AND a flag
    authority AND a P&I club involved at the same time, each doing
    something different and each potentially blocking a different
    WorkflowStepInstance.
    """
    class Role(models.TextChoices):
        HANDLING_LAWYER = "handling_lawyer", "Handling Lawyer"
        FLAG_AUTHORITY = "flag_authority", "Flag Authority"
        PNI_CLUB = "pni_club", "P&I Club"
        CLASS_SOCIETY = "class_society", "Classification Society"
        OTHER = "other", "Other"

    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE,
        related_name="organization_links",
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="service_request_links",
    )
    role = models.CharField(max_length=30, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service_request", "organization", "role"],
                name="unique_org_role_per_service_request",
            )
        ]

    def __str__(self):
        return f"{self.organization} as {self.role} on {self.service_request}"
