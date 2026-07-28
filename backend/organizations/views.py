from authorization.permissions import HasCapability
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from organizations import services as organization_services
from organizations.models import TenantFlagRelationship
from organizations.serializers import TenantFlagRelationshipSerializer
from rest_framework import status, viewsets
from rest_framework.response import Response


class TenantFlagRelationshipViewSet(viewsets.ModelViewSet):
    serializer_class = TenantFlagRelationshipSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "tenant_catalog.view",
        "retrieve": "tenant_catalog.view",
        "create": "tenant_catalog.manage",
        "update": "tenant_catalog.manage",
        "partial_update": "tenant_catalog.manage",
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return TenantFlagRelationship.objects.filter(tenant=self.request.user.tenant).select_related(
            "flag", "registry_organization", "partner_organization",
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relationship = organization_services.save_flag_relationship(
                tenant=request.user.tenant, data=serializer.validated_data,
            )
        except (organization_services.CrossTenantReferenceError, organization_services.FlagRelationshipValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(relationship).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        relationship = self.get_object()
        serializer = self.get_serializer(relationship, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            relationship = organization_services.save_flag_relationship(
                tenant=request.user.tenant, instance=relationship, data=serializer.validated_data,
            )
        except (organization_services.CrossTenantReferenceError, organization_services.FlagRelationshipValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(relationship).data)

    update = partial_update
