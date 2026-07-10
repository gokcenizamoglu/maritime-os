from config.permissions import IsSameTenantObject, IsTenantMember
from rest_framework import status as http_status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from workflow import services as workflow_services
from workflow.models import WorkflowStepInstance
from workflow.serializers import WorkflowStepInstanceSerializer, WorkflowStepTransitionSerializer
from workflow.state_machine import InvalidStepTransitionError


class WorkflowStepInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only for listing/inspecting; the only write path is the
    `transition` action, which routes through
    `workflow.services.update_step_status()` so guard validation and
    dependency-driven unblocking (`sync_step_statuses`) always run —
    never expose a generic PATCH here.
    """
    serializer_class = WorkflowStepInstanceSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject]

    def get_queryset(self):
        qs = WorkflowStepInstance.objects.filter(
            service_request__tenant=self.request.user.tenant
        ).select_related("step_template", "service_request", "assigned_organization")
        service_request_id = self.request.query_params.get("service_request")
        if service_request_id:
            qs = qs.filter(service_request_id=service_request_id)
        return qs

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        step_instance = self.get_object()
        serializer = WorkflowStepTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            workflow_services.update_step_status(
                step_instance=step_instance,
                status=serializer.validated_data["status"],
                actor_user=request.user,
            )
        except InvalidStepTransitionError as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(WorkflowStepInstanceSerializer(step_instance).data)
