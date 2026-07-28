from customers.models import Customer
from rest_framework import serializers

from vessels.models import Vessel


class VesselSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    current_flag_name = serializers.CharField(
        source="current_flag.name", read_only=True, allow_null=True,
    )

    class Meta:
        model = Vessel
        fields = [
            "id", "name", "imo_number", "customer", "customer_name",
            "current_flag", "current_flag_name", "vessel_type",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "customer_name", "current_flag_name", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        self._tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if self._tenant_id:
            self.fields["customer"].queryset = Customer.objects.filter(tenant_id=self._tenant_id)

    def validate_imo_number(self, value):
        qs = Vessel.objects.filter(tenant_id=self._tenant_id, imo_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A vessel with this IMO number already exists.")
        return value
