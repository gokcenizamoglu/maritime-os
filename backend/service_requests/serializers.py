from checklists.services import get_checklist_progress
from rest_framework import serializers
from service_requests.models import ServiceRequest


class ServiceRequestListSerializer(serializers.ModelSerializer):
    vessel_name = serializers.CharField(source="vessel.name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    service_type_name = serializers.CharField(source="service_type.name", read_only=True)
    flag_name = serializers.CharField(source="flag.name", read_only=True)

    class Meta:
        model = ServiceRequest
        fields = [
            "id", "reference_code", "status", "vessel_name", "customer_name",
            "service_type_name", "flag_name", "created_at",
        ]


class ServiceRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRequest
        fields = ["customer", "vessel", "service_type", "flag"]

    def __init__(self, *args, **kwargs):
        """
        REVIEW FIX (multi-tenant isolation, HIGH PRIORITY): previously
        `customer` and `vessel` were plain PrimaryKeyRelatedFields with
        the DEFAULT queryset (Customer.objects.all() / Vessel.objects.all())
        — meaning any authenticated user, from any tenant, could pass
        another tenant's customer_id/vessel_id and DRF would happily
        accept it as long as the PK existed anywhere in the database.
        The `vessel.customer == customer` check below caught *some*
        cross-tenant mismatches by accident, but a request using a
        different tenant's customer_id AND that same tenant's matching
        vessel_id would have sailed straight through.

        Fix: scope both querysets to request.user.tenant at
        instantiation time, so an out-of-tenant PK fails validation with
        a standard "does not exist" error before `validate()` even runs.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and hasattr(request.user, "tenant") and request.user.tenant_id:
            from customers.models import Customer
            from vessels.models import Vessel
            self.fields["customer"].queryset = Customer.objects.filter(tenant_id=request.user.tenant_id)
            self.fields["vessel"].queryset = Vessel.objects.filter(tenant_id=request.user.tenant_id)

    def validate(self, attrs):
        # Domain invariant check at the API boundary: a ServiceRequest's
        # vessel must actually belong to the given customer. This is
        # deliberately checked here (fast, request-scoped feedback)
        # rather than only as a DB constraint, since crossing customer/
        # vessel ownership is a user-facing input error, not a system bug.
        # (The tenant-membership check itself now happens via the scoped
        # querysets in __init__ above, plus defensively again in the
        # service layer — see service_requests.services.create_service_request.)
        if attrs["vessel"].customer_id != attrs["customer"].id:
            raise serializers.ValidationError("Vessel does not belong to the given customer.")
        return attrs


class ServiceRequestDetailSerializer(serializers.ModelSerializer):
    checklist_progress = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "id", "reference_code", "status", "customer", "vessel", "service_type",
            "flag", "created_at", "updated_at", "checklist_progress",
        ]

    def get_checklist_progress(self, obj):
        progress = get_checklist_progress(obj)
        return {"total": progress["total"], "complete": progress["complete"], "percent": progress["percent"]}


class TransitionStatusSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=ServiceRequest.Status.choices)
