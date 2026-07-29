from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    """
    Internal staff user (e.g. a Tarik-like ops coordinator).

    Customers are NOT Users — see customers.Customer. Customers never log
    in; they interact only through tokenized public upload links. Keeping
    these as separate models (rather than a shared "Person" with a role
    flag) avoids a whole class of authorization bugs where a customer
    accidentally gets internal-staff permissions because a role check
    was missed somewhere.
    """
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        OPS = "ops", "Operations"
        VIEWER = "viewer", "Viewer"

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="users",
        null=True, blank=True,  # null only for platform-level superusers
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPS)

    def __str__(self):
        return self.username

    def clean(self):
        super().clean()
        if (
            self.pk
            and self.role_assignments.exclude(role__tenant_id=self.tenant_id).exists()
        ):
            raise ValidationError(
                {"tenant": "The user's tenant must match every assigned tenant role."}
            )
