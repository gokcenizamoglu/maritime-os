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
    name = models.CharField(max_length=150, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

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
