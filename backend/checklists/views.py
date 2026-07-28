from authorization.permissions import HasCapability
from checklists import services as checklist_services
from checklists.models import ChecklistItem, ChecklistTemplate
from checklists.serializers import ChecklistItemSerializer, ChecklistTemplateDefinitionSerializer
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from rest_framework import viewsets
from rest_framework.response import Response


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
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    required_capability = "checklist.view"

    def get_queryset(self):
        qs = ChecklistItem.objects.filter(
            service_request__tenant=self.request.user.tenant
        ).select_related("document_type", "service_request")
        service_request_id = self.request.query_params.get("service_request")
        if service_request_id:
            qs = qs.filter(service_request_id=service_request_id)
        return qs


class ChecklistTemplateDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = ChecklistTemplateDefinitionSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "operation_template.view",
        "retrieve": "operation_template.view",
        "create": "operation_template.manage",
        "update": "operation_template.manage",
        "partial_update": "operation_template.manage",
        "destroy": "operation_template.manage",
    }

    def get_queryset(self):
        queryset = ChecklistTemplate.objects.filter(
            operation_template_version__operation_template__service_offering__tenant=self.request.user.tenant,
        ).select_related("operation_template_version__operation_template", "document_type")
        version_id = self.request.query_params.get("operation_template_version")
        return queryset.filter(operation_template_version_id=version_id) if version_id else queryset

    def _save(self, serializer, instance=None):
        return checklist_services.save_checklist_definition(
            tenant=self.request.user.tenant,
            data=serializer.validated_data,
            instance=instance,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            instance = self._save(serializer)
        except (checklist_services.ChecklistDefinitionValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(instance).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            instance = self._save(serializer, instance=instance)
        except (checklist_services.ChecklistDefinitionValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(instance).data)

    update = partial_update
