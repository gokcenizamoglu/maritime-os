from documents.models import Document
from rest_framework import serializers


class DocumentSerializer(serializers.ModelSerializer):
    """Read serializer. NOT used for creation — see InternalUploadSerializer.
    All fields here are read-only by construction (no `fields` that a
    client-side POST could abuse), which is itself part of the
    review fix for the upload-pipeline bypass (see documents.views)."""
    document_type_name = serializers.CharField(source="document_type.name", read_only=True, default=None)

    class Meta:
        model = Document
        fields = [
            "id", "original_filename", "file", "status", "document_type", "document_type_name",
            "predicted_document_type", "classification_confidence",
            "checklist_item", "uploaded_by_type", "created_at", "is_superseded",
        ]
        read_only_fields = fields  # this serializer is read-only end to end


class InternalUploadSerializer(serializers.Serializer):
    """
    REVIEW FIX (#2, document upload pipeline): previously
    `DocumentViewSet.create` (inherited from ModelViewSet) let an
    authenticated internal user POST a `Document` directly via
    `DocumentSerializer`, writing straight to the model with
    `.save()` — completely bypassing `documents.services.upload_document`,
    which means NO activity log entry was created and NO checklist
    matching occurred for internally-uploaded documents. This
    serializer is deliberately input-only and minimal; `documents.views`
    now routes every field it collects through the service layer instead
    of calling `serializer.save()`.
    """
    service_request = serializers.IntegerField()
    file = serializers.FileField()


class PublicUploadSerializer(serializers.Serializer):
    """
    Used on the no-login customer upload endpoint. Deliberately accepts
    only a file — everything else (tenant, service_request, uploaded_by)
    is derived server-side from the validated UploadLink token, never
    from client input.
    """
    file = serializers.FileField()


class ClassifyDocumentSerializer(serializers.Serializer):
    document_type_id = serializers.IntegerField()
    mark_validated = serializers.BooleanField(default=False)
