from config.pagination import StandardResultsPagination
from config.permissions import IsSameTenantObject, IsTenantMember
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets, status
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

    LIST HARDENING (pagination/filter/search/ordering sprint): `list()`
    is the only action DRF actually routes through `filter_backends` /
    `pagination_class` (ListModelMixin calls `self.filter_queryset(...)`
    and `self.paginate_queryset(...)` itself) — `retrieve`, `create`, and
    the `transition` action below are untouched by any of this. The
    LIST/DETAIL SERIALIZER SHAPES ARE DELIBERATELY UNCHANGED in this
    sprint (see ServiceRequestListSerializer / ServiceRequestDetailSerializer
    — not touched here) to avoid a second breaking change landing on the
    frontend at the same time as pagination; that inconsistency is a
    separate, already-identified follow-up.

    Every filter/search/order operates on TOP of the tenant-scoped
    queryset from get_queryset() below — DjangoFilterBackend/SearchFilter/
    OrderingFilter narrow an already-tenant-filtered queryset, they never
    replace it, so no query parameter can widen results beyond the
    caller's own tenant. `filterset_fields` deliberately never includes
    `tenant` itself.
    """
    permission_classes = [IsTenantMember, IsSameTenantObject]
    http_method_names = ["get", "post", "patch"]  # no raw PUT/DELETE — deletion is a domain decision, not a Phase 1 feature
    pagination_class = StandardResultsPagination

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "vessel", "service_type", "flag"]
    search_fields = [
        "reference_code", "customer__name", "vessel__name",
        "service_type__name", "flag__name",
    ]
    ordering_fields = ["created_at", "updated_at", "reference_code", "status"]
    # No explicit `ordering` default here: ServiceRequest.Meta.ordering
    # (-created_at) already applies whenever the client doesn't pass
    # ?ordering=, so restating it would just be a second source of truth.

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
