from authorization.permissions import HasCapability
from catalog import services as catalog_services
from catalog.models import TenantServiceOffering
from catalog.serializers import TenantServiceOfferingSerializer
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from workflow.models import OperationTemplate, OperationTemplateVersion


class TenantServiceOfferingViewSet(viewsets.ModelViewSet):
    serializer_class = TenantServiceOfferingSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "tenant_catalog.view",
        "retrieve": "tenant_catalog.view",
        "available": "tenant_catalog.view",
        "create": "tenant_catalog.manage",
        "update": "tenant_catalog.manage",
        "partial_update": "tenant_catalog.manage",
        "accept_new_requests": "tenant_catalog.manage",
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        published_versions = OperationTemplateVersion.objects.filter(
            status=OperationTemplateVersion.Status.PUBLISHED,
        ).order_by("-version_number")
        templates = OperationTemplate.objects.prefetch_related(
            Prefetch("versions", queryset=published_versions, to_attr="published_versions"),
        )
        return TenantServiceOffering.objects.filter(tenant=self.request.user.tenant).select_related(
            "service_type", "flag", "flag_relationship__registry_organization",
            "flag_relationship__partner_organization",
        ).prefetch_related(Prefetch("operation_templates", queryset=templates))

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

    @action(detail=False, methods=["get"])
    def available(self, request):
        offerings = [
            offering for offering in self.get_queryset()
            if offering.is_available_for_new_requests()
        ]
        return Response(self.get_serializer(offerings, many=True).data)

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
