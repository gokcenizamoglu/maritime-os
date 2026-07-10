from config.base_models import TenantScopedModel
from django.db import models


class Vessel(TenantScopedModel):
    """
    A ship. Deliberately has NO pointer to "its current ServiceRequest" —
    a Vessel can have many open ServiceRequests simultaneously (Owner
    Change + Crew Endorsement + Radio License, all in parallel). Any
    "vessel status" view must aggregate across ServiceRequest.objects
    .filter(vessel=self), never read a cached field on Vessel itself.
    Adding such a field is the single most tempting shortcut a future
    engineer will take — don't.
    """
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="vessels",
        help_text="The owning/operating customer.",
    )
    name = models.CharField(max_length=255)
    imo_number = models.CharField(
        max_length=20,
        help_text="Uniqueness is enforced PER TENANT (see Meta.constraints), not "
                   "globally. REVIEW NOTE: IMO numbers are globally unique in the "
                   "real world, but this platform is multi-tenant B2B SaaS — the "
                   "same physical vessel can legitimately be a client of two "
                   "different, unrelated maritime consultancies (e.g. switching "
                   "agents, or using two agents for different flag jurisdictions). "
                   "A global unique constraint would let Tenant A's vessel record "
                   "block Tenant B from ever registering the same ship — a hard "
                   "outage for a paying customer. Cross-tenant duplicate detection "
                   "(useful for platform analytics) belongs in a reporting query, "
                   "not a blocking DB constraint.",
    )
    current_flag = models.ForeignKey(
        "catalog.Flag", on_delete=models.PROTECT, related_name="vessels",
        null=True, blank=True,
        help_text="The vessel's flag today. A ServiceRequest carries its "
                   "own Flag independently — e.g. a Change-of-Flag request "
                   "targets a DIFFERENT flag than current_flag.",
    )
    vessel_type = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "imo_number"], name="unique_imo_per_tenant"),
        ]

    def __str__(self):
        return f"{self.name} (IMO {self.imo_number})"
