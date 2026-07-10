import uuid

from config.base_models import TenantScopedModel
from django.conf import settings
from django.db import models
from django.utils import timezone


def document_upload_path(instance, filename):
    return f"tenants/{instance.tenant_id}/service_requests/{instance.service_request_id}/{uuid.uuid4()}_{filename}"


class Document(TenantScopedModel):
    """
    A single uploaded file plus its metadata and classification state.

    Lifecycle (independent of ChecklistItem completion, which is
    computed FROM this):
        unclassified -> classified -> validated

    Design decisions worth flagging:
      - `document_type` is NULLABLE. Upload and classification are two
        separate events in time — a document sits unclassified in the
        inbox until an internal user (or, in Phase 2, an AI classifier)
        maps it.
      - `checklist_item` is a separate FK from `document_type`. A
        Document can be classified (document_type set) WITHOUT yet being
        linked to a specific ChecklistItem slot, e.g. when a
        ServiceRequest requires 3 passport copies (min_count=3) and this
        is the 2nd one uploaded — the mapping records which slot it
        fills.
      - `supersedes` models versioning/correction: a wrong Bill of Sale
        gets replaced by a corrected one without losing history. The
        checklist recompute logic only counts the latest, non-superseded
        version of each document toward completion.
      - `predicted_document_type` / `classification_confidence` exist now,
        unused in Phase 1 UI, purely so Phase 2's AI classifier can write
        a suggestion here WITHOUT touching `document_type` (the confirmed
        field) or requiring an additive migration on a hot table later.
        REVIEW NOTE: originally this used a separate `classification_source`
        enum (manual/ai). Removed — it was an abstraction with no current
        consumer. Whether a classification was manual or AI-suggested is
        already implicit: `predicted_document_type` set + `document_type`
        unset/different = an unconfirmed AI suggestion; `document_type` set
        = confirmed (by whoever called classify_document, human or system).
        Re-add a source enum only when a second automated classifier with
        a genuinely different confidence model exists — not preemptively.
    """
    class Status(models.TextChoices):
        UNCLASSIFIED = "unclassified", "Unclassified"
        CLASSIFIED = "classified", "Classified"
        VALIDATED = "validated", "Validated"

    class UploadedByType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        INTERNAL = "internal", "Internal Staff"
        SYSTEM = "system", "System (e.g. email ingestion)"

    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.CASCADE, related_name="documents",
    )
    document_type = models.ForeignKey(
        "catalog.DocumentType", on_delete=models.PROTECT, related_name="documents",
        null=True, blank=True,
        help_text="CONFIRMED type. Set only via documents.services.classify_document().",
    )
    predicted_document_type = models.ForeignKey(
        "catalog.DocumentType", on_delete=models.SET_NULL, related_name="predicted_documents",
        null=True, blank=True,
        help_text="Phase 2: an AI classifier's suggestion, prior to human/system "
                   "confirmation. Never read by checklist recompute logic — only "
                   "`document_type` (confirmed) counts toward completion.",
    )
    checklist_item = models.ForeignKey(
        "checklists.ChecklistItem", on_delete=models.SET_NULL, related_name="documents",
        null=True, blank=True,
    )
    file = models.FileField(upload_to=document_upload_path)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNCLASSIFIED)

    uploaded_by_type = models.CharField(max_length=20, choices=UploadedByType.choices)
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_documents",
        help_text="Set only when uploaded_by_type=internal.",
    )

    supersedes = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="superseded_by_set",
        help_text="Points to the older version this document corrects/replaces.",
    )
    source_email = models.ForeignKey(
        "emails.EmailMessage", on_delete=models.SET_NULL, null=True, blank=True, related_name="extracted_documents",
        help_text="Phase 2: set when this Document was auto-extracted from an "
                   "email attachment by the ingestion pipeline. Null for portal "
                   "uploads and internal-staff uploads. Added now so the ingestion "
                   "feature is additive, not a migration on a hot table later.",
    )

    classification_confidence = models.FloatField(
        null=True, blank=True,
        help_text="Confidence score for predicted_document_type. Meaningless "
                   "once document_type is confirmed.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["service_request", "status"]),
            models.Index(fields=["checklist_item"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"

    @property
    def is_superseded(self) -> bool:
        return self.superseded_by_set.exists()


class UploadLink(TenantScopedModel):
    """
    A secure, tokenized, no-login link for a customer to upload
    documents against a specific ServiceRequest.

    One-to-one with ServiceRequest by design in Phase 1 (one active link
    per case). If multiple simultaneous links per case are ever needed
    (e.g. separate links per crew member), that's a straightforward
    FK-instead-of-OneToOne change later — noted here so nobody is
    surprised by it.
    """
    service_request = models.OneToOneField(
        "service_requests.ServiceRequest", on_delete=models.CASCADE, related_name="upload_link",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)

    def is_valid(self) -> bool:
        return (not self.is_revoked) and timezone.now() < self.expires_at

    def __str__(self):
        return f"Upload link for {self.service_request.reference_code}"
