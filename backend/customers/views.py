from authorization.permissions import HasCapability
from config.pagination import StandardResultsPagination
from config.permissions import IsSameTenantObject, IsTenantMember
from rest_framework import filters, viewsets
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.viewsets import GenericViewSet

from customers.models import Customer
from customers.serializers import CustomerSerializer


class CustomerViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    CreateModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "customer.view",
        "retrieve": "customer.view",
        "create": "customer.create",
        "update": "customer.update",
        "partial_update": "customer.update",
    }
    serializer_class = CustomerSerializer
    pagination_class = StandardResultsPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "contact_email"]
    ordering_fields = ["name", "created_at"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return Customer.objects.filter(tenant=self.request.user.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
