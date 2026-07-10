from django.db import models


class Tenant(models.Model):
    """
    A maritime consultancy company using the platform (e.g. Liva Marine).

    Deliberately minimal in Phase 1. This is the anchor every other
    tenant-scoped model hangs off of. Billing plan, feature flags, and
    branding config are Phase 2+ concerns and should live on a related
    TenantSettings model, not bolted onto this one, so that Tenant itself
    stays a stable, rarely-migrated table.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
