from catalog.models import DocumentType
from config.pagination import StandardResultsPagination
from config.permissions import IsSameTenantObject, IsTenantMember
from django.http import Http404
from django.shortcuts import get_object_or_404
from documents import services as document_services
from documents.models import Document, UploadLink
from documents.serializers import (
    ClassifyDocumentSerializer,
    DocumentSerializer,
    InternalUploadSerializer,
    PublicUploadSerializer,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from service_requests.models import ServiceRequest


class DocumentViewSet(viewsets.ModelViewSet):
    """
    Internal, authenticated document management (view uploads, classify).

    REVIEW FIX (#2): `create()` is overridden below instead of relying on
    ModelViewSet's default, which would call `DocumentSerializer.save()`
    directly against the model — bypassing activity logging and
    checklist matching entirely for anything uploaded by internal staff
    through this endpoint (as opposed to the public customer portal,
    which already went through the service layer correctly). Every
    document, regardless of entry point, now goes through
    `documents.services.upload_document()`.
    """
    permission_classes = [IsTenantMember, IsSameTenantObject]
    serializer_class = DocumentSerializer
    http_method_names = ["get", "post"]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        queryset = Document.objects.filter(
            tenant=self.request.user.tenant
        ).select_related("document_type", "predicted_document_type", "service_request")

        service_request_id = self.request.query_params.get("service_request")
        if service_request_id is not None:
            # Deliberately narrower than ServiceRequestViewSet's filtering
            # (that one's a full DjangoFilterBackend setup) — this sprint
            # only asked for ONE Document filter. Validates the referenced
            # ServiceRequest exists AND belongs to this tenant, using the
            # SAME convention as create() below (get_object_or_404 against
            # a tenant-filtered queryset) — an out-of-tenant or nonexistent
            # id 404s rather than silently returning an empty list, which
            # would look identical to "this case genuinely has no
            # documents" instead of "you don't have access to that case."
            if not service_request_id.isdigit():
                raise Http404("Invalid service_request id.")
            get_object_or_404(
                ServiceRequest.objects.filter(tenant=self.request.user.tenant),
                pk=service_request_id,
            )
            queryset = queryset.filter(service_request_id=service_request_id)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = InternalUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Tenant scoping: service_request must belong to the caller's
        # tenant. get_object_or_404 against a tenant-filtered queryset
        # means an out-of-tenant id 404s rather than silently succeeding.
        service_request = get_object_or_404(
            ServiceRequest.objects.filter(tenant=request.user.tenant),
            pk=serializer.validated_data["service_request"],
        )
        uploaded_file = serializer.validated_data["file"]

        document = document_services.upload_document(
            service_request=service_request,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            uploaded_by_type=Document.UploadedByType.INTERNAL,
            uploaded_by_user=request.user,
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="classify")
    def classify(self, request, pk=None):
        document = self.get_object()
        serializer = ClassifyDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Tenant-scoped lookup: a DocumentType is global reference data
        # so no tenant filter applies to it directly, but `document` was
        # already resolved via the tenant-filtered get_queryset() above,
        # so classification can only ever be applied to an in-tenant document.
        document_type = get_object_or_404(
            DocumentType, id=serializer.validated_data["document_type_id"]
        )
        document_services.classify_document(
            document=document,
            document_type=document_type,
            actor_user=request.user,
            mark_validated=serializer.validated_data["mark_validated"],
        )
        return Response(DocumentSerializer(document).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def public_upload_view(request, token):
    """
    The customer-facing, no-login upload endpoint. Security lives
    entirely in the UploadLink token (UUID, expiry, revocation) rather
    than any session/auth — this is the "secure link, no login required"
    requirement.
    """
    upload_link = get_object_or_404(UploadLink, token=token)
    if not upload_link.is_valid():
        return Response({"detail": "This upload link has expired or been revoked."}, status=status.HTTP_410_GONE)

    serializer = PublicUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    uploaded_file = serializer.validated_data["file"]

    document = document_services.upload_document(
        service_request=upload_link.service_request,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        uploaded_by_type=Document.UploadedByType.CUSTOMER,
    )
    return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)
