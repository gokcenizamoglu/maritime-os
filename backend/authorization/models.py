from config.base_models import TimeStampedModel, TenantScopedModel
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Capability(TimeStampedModel):
    """
    A platform-defined permission unit, synchronized from the code
    registry (authorization.registry.CAPABILITY_REGISTRY).

    Tenants cannot create Capability rows — they can only assign existing
    ones to their roles via RoleCapability. The code field is the stable
    identifier used in permission checks; the label/description are for
    admin UI display.
    """
    code = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100)
    module_code = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    is_deprecated = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class TenantRole(TenantScopedModel):
    """
    A role owned by a specific tenant. Role names are unique within a
    tenant but different tenants can have identically named roles.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_system_default = models.BooleanField(
        default=False,
        help_text="True for roles created by provision_default_roles(). "
                  "These can still be edited by tenant admins — the flag "
                  "is informational, not a write-lock.",
    )
    is_active = models.BooleanField(default=True)
    capabilities = models.ManyToManyField(
        Capability, through="RoleCapability", related_name="roles", blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="unique_role_name_per_tenant",
            ),
        ]
        ordering = ["tenant", "name"]

    def __str__(self):
        return f"{self.name} ({self.tenant})"

    def clean(self):
        super().clean()
        if (
            self.pk
            and self.user_assignments.exclude(user__tenant_id=self.tenant_id).exists()
        ):
            raise ValidationError(
                {"tenant": "A role with user assignments cannot move to another tenant."}
            )


class RoleCapability(TimeStampedModel):
    """
    Join model granting a specific Capability to a TenantRole.
    Deleting a TenantRole cascades here but never touches Capability.
    """
    role = models.ForeignKey(
        TenantRole, on_delete=models.CASCADE, related_name="role_capabilities",
    )
    capability = models.ForeignKey(
        Capability, on_delete=models.PROTECT, related_name="role_capability_assignments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "capability"],
                name="unique_capability_per_role",
            ),
        ]

    def __str__(self):
        return f"{self.role.name} -> {self.capability.code}"


class UserRoleAssignment(TimeStampedModel):
    """
    Assigns a user to a TenantRole. A user may have multiple roles;
    effective capabilities are the union of all assigned role capabilities.

    The tenant consistency constraint (user.tenant == role.tenant) is
    enforced by authorization.services, not by a DB constraint, because
    the user's tenant FK lives on a different table. The unique constraint
    prevents duplicate assignments.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        TenantRole, on_delete=models.CASCADE, related_name="user_assignments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                name="unique_user_role_assignment",
            ),
        ]

    def __str__(self):
        return f"{self.user} -> {self.role.name}"

    def clean(self):
        super().clean()
        if self.user_id and self.role_id and self.user.tenant_id != self.role.tenant_id:
            raise ValidationError(
                {"role": "The assigned role must belong to the user's tenant."}
            )
