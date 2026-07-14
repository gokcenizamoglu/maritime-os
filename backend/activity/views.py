from activity.models import ActivityLog
from activity.services import build_timeline_entry
from authorization.permissions import HasCapability
from config.permissions import IsTenantMember
from rest_framework.response import Response
from rest_framework.views import APIView


class ServiceRequestTimelineView(APIView):
    """
    ARCHITECTURAL ADDITION (Activity Log -> Timeline System): a thin
    read endpoint over `build_timeline_entry()`. Deliberately a plain
    `APIView`, not a `ModelViewSet` — this is a query over an existing
    log, not a resource with its own CRUD lifecycle.
    """
    permission_classes = [IsTenantMember, HasCapability]
    required_capability = "activity.view"

    def get(self, request, service_request_id):
        from django.shortcuts import get_object_or_404
        from service_requests.models import ServiceRequest

        service_request = get_object_or_404(
            ServiceRequest.objects.filter(tenant=request.user.tenant), pk=service_request_id,
        )
        logs = ActivityLog.objects.filter(service_request=service_request).select_related("actor_user")
        return Response([build_timeline_entry(log) for log in logs])
