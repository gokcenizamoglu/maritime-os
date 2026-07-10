"""
Shared abstract base classes used across every domain app.

These exist so that cross-cutting concerns (tenant scoping, timestamps,
soft-delete later) are defined ONCE and inherited everywhere, rather than
copy-pasted per model. This is a Phase-1 decision that pays off the moment
you add row-level tenant isolation, audit trails, or soft-deletes later —
you change it here, not in nine different models.py files.
"""
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopedModel(TimeStampedModel):
    """
    Every core business entity belongs to exactly one Tenant (company).

    NOTE: this is a hard multi-tenancy boundary at the ORM level. Every
    manager/queryset that touches tenant-scoped models should be filtered
    by tenant at the view/service layer — never trust a client-supplied
    tenant_id. In Phase 2 this is also the natural hook point for
    row-level security if you migrate to Postgres RLS.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
    )

    class Meta:
        abstract = True
