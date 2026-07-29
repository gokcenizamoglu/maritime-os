from config.base_models import TenantScopedModel
from django.core.exceptions import ValidationError
from django.db import models


class Customer(TenantScopedModel):
    """
    The vessel owner / operator company that requests services.

    A Customer can own multiple Vessels and raise ServiceRequests across
    any of them. Contact details live here rather than on Vessel, since
    the commercial relationship is with the Customer, not the ship.
    """
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.pk:
            return
        original = type(self).objects.get(pk=self.pk)
        if (
            original.tenant_id != self.tenant_id
            and (self.vessels.exists() or self.service_requests.exists())
        ):
            raise ValidationError(
                {"tenant": "A customer with vessels or service requests cannot move tenants."}
            )
