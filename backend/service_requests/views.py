from config.permissions import IsSameTenantObject, IsTenantMember
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from service_requests import services as service_request_services
from service_requests.models import ServiceRequest
from service_requests.serializers import (
    ServiceRequestCreateSerializer,
    ServiceRequestDetailSerializer,
    ServiceRequestListSerializer,
    TransitionStatusSerializer,
)
from service_requests.state_machine import InvalidTransitionError, TransitionGuardError


class ServiceRequestViewSet(viewsets.ModelViewSet):
    """
    Deliberately thin: every non-trivial operation delegates to
    service_requests.services. The view's job is HTTP concerns
    (permissions, status codes, serialization) — never business logic.

    REVIEW FIX (#8): added IsSameTenantObject as an explicit object-level
    backstop behind the tenant-filtered get_queryset() below — see
    config.permissions for why both matter.
    """
    permission_classes = [IsTenantMember, IsSameTenantObject]
    http_method_names = ["get", "post", "patch"]  # no raw PUT/DELETE — deletion is a domain decision, not a Phase 1 feature

    def get_queryset(self):
        # Tenant scoping enforced here, never trusted from the client.
        return ServiceRequest.objects.filter(
            tenant=self.request.user.tenant
        ).select_related("customer", "vessel", "service_type", "flag")

    def get_serializer_class(self):
        if self.action == "list":
            return ServiceRequestListSerializer
        if self.action == "create":
            return ServiceRequestCreateSerializer
        return ServiceRequestDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service_request = service_request_services.create_service_request(
            tenant=request.user.tenant,
            created_by=request.user,
            **serializer.validated_data,
        )
        output = ServiceRequestDetailSerializer(service_request)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        service_request = self.get_object()
        serializer = TransitionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service_request_services.transition_state(
                service_request=service_request,
                target_status=serializer.validated_data["target_status"],
                actor_user=request.user,
            )
        except (InvalidTransitionError, TransitionGuardError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ServiceRequestDetailSerializer(service_request).data)
