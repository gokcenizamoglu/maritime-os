from authorization.permissions import HasCapability
from config.permissions import IsSameTenantObject, IsTenantMember
from django.db import IntegrityError
from rest_framework import status as http_status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from workflow import services as workflow_services
from workflow.models import OperationTemplate, OperationTemplateVersion, WorkflowStepInstance, WorkflowStepTemplate
from workflow.serializers import (
    OperationTemplateSerializer,
    OperationTemplateVersionSerializer,
    WorkflowStepInstanceSerializer,
    WorkflowStepTemplateDefinitionSerializer,
    WorkflowStepTransitionSerializer,
)
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
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "workflow.view",
        "retrieve": "workflow.view",
        "transition": "workflow.advance",
    }

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


class OperationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = OperationTemplateSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "operation_template.view",
        "retrieve": "operation_template.view",
        "versions": "operation_template.view",
        "create": "operation_template.manage",
        "update": "operation_template.manage",
        "partial_update": "operation_template.manage",
        "create_draft": "operation_template.manage",
        "set_default": "operation_template.manage",
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return OperationTemplate.objects.filter(
            service_offering__tenant=self.request.user.tenant,
        ).select_related("service_offering").prefetch_related("versions")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            template = workflow_services.save_operation_template(
                tenant=request.user.tenant, data=serializer.validated_data,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(template).data, status=http_status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        template = self.get_object()
        serializer = self.get_serializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            template = workflow_services.save_operation_template(
                tenant=request.user.tenant, instance=template, data=serializer.validated_data,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(template).data)

    update = partial_update

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        template = self.get_object()
        versions = template.versions.order_by("-version_number")
        return Response(OperationTemplateVersionSerializer(versions, many=True).data)

    @action(detail=True, methods=["post"], url_path="create-draft")
    def create_draft(self, request, pk=None):
        template = self.get_object()
        try:
            version = workflow_services.create_draft_version(
                tenant=request.user.tenant, operation_template=template, created_by=request.user,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(OperationTemplateVersionSerializer(version).data, status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def set_default(self, request, pk=None):
        template = self.get_object()
        try:
            template = workflow_services.set_default_template(
                tenant=request.user.tenant, operation_template=template,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(template).data)


class OperationTemplateVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OperationTemplateVersionSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "operation_template.view",
        "retrieve": "operation_template.view",
        "clone": "operation_template.manage",
        "publish": "operation_template.publish",
        "retire": "operation_template.publish",
        "archive": "operation_template.publish",
    }

    def get_queryset(self):
        return OperationTemplateVersion.objects.filter(
            operation_template__service_offering__tenant=self.request.user.tenant,
        ).select_related("operation_template__service_offering", "created_by", "published_by")

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        source = self.get_object()
        try:
            version = workflow_services.clone_published_version(
                tenant=request.user.tenant, source_version=source, created_by=request.user,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(version).data, status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        version = self.get_object()
        try:
            version = workflow_services.publish_version(
                tenant=request.user.tenant, version=version, published_by=request.user,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(version).data)

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        version = self.get_object()
        try:
            version = workflow_services.retire_version(
                tenant=request.user.tenant, version=version,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(version).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        version = self.get_object()
        try:
            version = workflow_services.archive_version(
                tenant=request.user.tenant, version=version,
            )
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(version).data)


class WorkflowStepTemplateDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowStepTemplateDefinitionSerializer
    permission_classes = [IsTenantMember, IsSameTenantObject, HasCapability]
    capability_map = {
        "list": "operation_template.view",
        "retrieve": "operation_template.view",
        "create": "operation_template.manage",
        "update": "operation_template.manage",
        "partial_update": "operation_template.manage",
        "destroy": "operation_template.manage",
    }

    def get_queryset(self):
        queryset = WorkflowStepTemplate.objects.filter(
            operation_template_version__operation_template__service_offering__tenant=self.request.user.tenant,
        ).select_related("operation_template_version__operation_template")
        version_id = self.request.query_params.get("operation_template_version")
        return queryset.filter(operation_template_version_id=version_id) if version_id else queryset

    def _save(self, serializer, instance=None):
        data = dict(serializer.validated_data)
        dependency_codes = data.pop("depends_on_codes", None)
        return workflow_services.save_workflow_definition(
            tenant=self.request.user.tenant, data=data,
            dependency_codes=dependency_codes, instance=instance,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            instance = self._save(serializer)
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(instance).data, status=http_status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            instance = self._save(serializer, instance=instance)
        except (workflow_services.OperationTemplateValidationError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(instance).data)

    update = partial_update
