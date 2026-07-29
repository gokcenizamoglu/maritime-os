from config.base_models import TenantScopedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TenantFlagRelationship(TenantScopedModel):
    """A tenant's relationship with a flag/registry network.

    Multiple rows for one flag are deliberate: a tenant can use more than
    one correspondent or partner for the same registry. The database
    identity therefore includes the relationship kind and organization
    references instead of incorrectly enforcing ``unique(tenant, flag)``.
    """

    class RelationshipType(models.TextChoices):
        DIRECT = "direct", "Direct"
        AUTHORIZED_REPRESENTATIVE = "authorized_representative", "Authorized representative"
        CORRESPONDENT = "correspondent", "Correspondent"
        PARTNER = "partner", "Partner"
        REFERRAL = "referral", "Referral"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.PROTECT, related_name="tenant_relationships",
    )
    relationship_type = models.CharField(max_length=35, choices=RelationshipType.choices)
    registry_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT,
        related_name="registry_relationships", null=True, blank=True,
    )
    partner_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT,
        related_name="partner_relationships", null=True, blank=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INACTIVE)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["flag__name", "relationship_type", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "flag", "relationship_type"],
                condition=Q(registry_organization__isnull=True, partner_organization__isnull=True),
                name="unique_direct_flag_relationship",
            ),
            models.UniqueConstraint(
                fields=["tenant", "flag", "relationship_type", "registry_organization"],
                condition=Q(registry_organization__isnull=False, partner_organization__isnull=True),
                name="unique_registry_flag_relationship",
            ),
            models.UniqueConstraint(
                fields=["tenant", "flag", "relationship_type", "partner_organization"],
                condition=Q(registry_organization__isnull=True, partner_organization__isnull=False),
                name="unique_partner_flag_relationship",
            ),
            models.UniqueConstraint(
                fields=[
                    "tenant", "flag", "relationship_type",
                    "registry_organization", "partner_organization",
                ],
                condition=Q(registry_organization__isnull=False, partner_organization__isnull=False),
                name="unique_network_flag_relationship",
            ),
        ]

    def __str__(self):
        return f"{self.tenant} / {self.flag} ({self.relationship_type})"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.tenant_id
            and self.registry_organization_id
            and self.registry_organization.tenant_id != self.tenant_id
        ):
            errors["registry_organization"] = (
                "The registry organization must belong to the relationship tenant."
            )
        if (
            self.tenant_id
            and self.partner_organization_id
            and self.partner_organization.tenant_id != self.tenant_id
        ):
            errors["partner_organization"] = (
                "The partner organization must belong to the relationship tenant."
            )
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            if (
                (original.tenant_id != self.tenant_id or original.flag_id != self.flag_id)
                and self.service_offerings.exists()
            ):
                errors["tenant"] = (
                    "A flag relationship used by an offering cannot change tenant or flag."
                )
        if errors:
            raise ValidationError(errors)

    def is_available_for_new_requests(self, *, today=None) -> bool:
        today = today or timezone.localdate()
        return (
            self.status == self.Status.ACTIVE
            and (self.valid_from is None or self.valid_from <= today)
            and (self.valid_until is None or self.valid_until >= today)
        )


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

    def clean(self):
        super().clean()
        if not self.pk:
            return
        original = type(self).objects.get(pk=self.pk)
        has_references = (
            self.registry_relationships.exists()
            or self.partner_relationships.exists()
            or self.service_request_links.exists()
            or self.assigned_workflow_steps.exists()
        )
        if original.tenant_id != self.tenant_id and has_references:
            raise ValidationError(
                {"tenant": "A referenced organization cannot move to another tenant."}
            )


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
