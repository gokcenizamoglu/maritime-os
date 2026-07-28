from authorization.permissions import HasCapability
from config.pagination import StandardResultsPagination
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, status
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from vessels.models import Vessel
from vessels.serializers import VesselSerializer


class VesselViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    CreateModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "vessel.view",
        "retrieve": "vessel.view",
        "create": "vessel.create",
        "update": "vessel.update",
        "partial_update": "vessel.update",
    }
    serializer_class = VesselSerializer
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["customer"]
    search_fields = ["name", "imo_number"]
    ordering_fields = ["name", "created_at"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return Vessel.objects.filter(
            tenant=self.request.user.tenant,
        ).select_related("customer", "current_flag")

    def perform_create(self, serializer):
        try:
            serializer.save(tenant=self.request.user.tenant)
        except IntegrityError:
            raise

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {"imo_number": ["A vessel with this IMO number already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"imo_number": ["A vessel with this IMO number already exists."]}
            ) from exc
