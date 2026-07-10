from checklists.models import ChecklistItem
from checklists.serializers import ChecklistItemSerializer
from config.permissions import IsSameTenantObject, IsTenantMember
from rest_framework import viewsets


class ChecklistItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only: checklist items are never edited directly through the API
    — they're generated (checklists.services.generate_checklist_for_service_request)
    and recomputed (recompute_checklist_item) as side effects of document
    classification. Exposing a write endpoint here would let a client
    bypass the derivation logic and set is_complete=True by hand.

    ChecklistItem has no direct `tenant` field (it belongs to a
    ServiceRequest, which is tenant-scoped) — IsSameTenantObject's
    fallback to `obj.service_request.tenant_id` handles that; see
    config.permissions.
    """
    serializer_class = ChecklistItemSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject]

    def get_queryset(self):
        qs = ChecklistItem.objects.filter(
            service_request__tenant=self.request.user.tenant
        ).select_related("document_type", "service_request")
        service_request_id = self.request.query_params.get("service_request")
        if service_request_id:
            qs = qs.filter(service_request_id=service_request_id)
        return qs
