from authorization.permissions import HasCapability
from catalog import services as catalog_services
from catalog.models import TenantServiceOffering
from catalog.serializers import TenantServiceOfferingSerializer
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response


class TenantServiceOfferingViewSet(viewsets.ModelViewSet):
    serializer_class = TenantServiceOfferingSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "tenant_catalog.view",
        "retrieve": "tenant_catalog.view",
        "create": "tenant_catalog.manage",
        "update": "tenant_catalog.manage",
        "partial_update": "tenant_catalog.manage",
        "accept_new_requests": "tenant_catalog.manage",
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return TenantServiceOffering.objects.filter(tenant=self.request.user.tenant).select_related(
            "service_type", "flag", "flag_relationship__registry_organization",
            "flag_relationship__partner_organization",
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            offering = catalog_services.save_offering(
                tenant=request.user.tenant, data=serializer.validated_data,
            )
        except (catalog_services.OfferingValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(offering).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        offering = self.get_object()
        serializer = self.get_serializer(offering, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            offering = catalog_services.save_offering(
                tenant=request.user.tenant, instance=offering, data=serializer.validated_data,
            )
        except (catalog_services.OfferingValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(offering).data)

    update = partial_update

    @action(detail=True, methods=["post"], url_path="accept-new-requests")
    def accept_new_requests(self, request, pk=None):
        offering = self.get_object()
        serializer = self.get_serializer(
            offering, data={"accepts_new_requests": request.data.get("accepts_new_requests")}, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        try:
            offering = catalog_services.save_offering(
                tenant=request.user.tenant, instance=offering, data=serializer.validated_data,
            )
        except (catalog_services.OfferingValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(offering).data)
