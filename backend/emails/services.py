"""
The service interface a future email-ingestion worker will call.

NOT implemented here: connecting to a mailbox, parsing MIME, matching
heuristics (subject reference-code regex, sender-address lookup,
thread-ID continuity). Those are Phase 2 concerns that live in an
adapter which calls the two functions below — kept deliberately thin so
that adapter is the only thing that needs building later.
"""
from django.db import transaction
from documents import services as document_services
from documents.models import Document
from emails.models import EmailMessage


def ingest_email(*, tenant, external_message_id: str, from_address: str, subject: str,
                  received_at, raw_body_storage_key: str, service_request=None) -> EmailMessage:
    """
    Record an inbound email. `service_request` is optional — if the
    (not-yet-built) matching logic already knows which case this
    belongs to, pass it; otherwise it lands as UNMATCHED for manual
    triage. Idempotent on `external_message_id`.
    """
    email_message, _ = EmailMessage.objects.get_or_create(
        external_message_id=external_message_id,
        defaults={
            "tenant": tenant,
            "from_address": from_address,
            "subject": subject,
            "received_at": received_at,
            "raw_body_storage_key": raw_body_storage_key,
            "service_request": service_request,
            "status": EmailMessage.Status.MATCHED if service_request else EmailMessage.Status.UNMATCHED,
        },
    )
    return email_message


@transaction.atomic
def extract_documents_from_email(*, email_message: EmailMessage, attachments: list[dict]) -> list[Document]:
    """
    Turn an email's attachments into normal Documents on its matched
    ServiceRequest, reusing `upload_document()` — an extracted
    attachment gets the SAME activity-logged, checklist-aware treatment
    as a portal or internal upload.

    `attachments` is a list of `{"file": <File-like>, "filename": str}`
    dicts — deliberately a plain structure, not a new model, since an
    attachment's only job here is to become a Document.

    Raises if the email isn't matched to a ServiceRequest yet — this
    function is the LAST step of ingestion (after matching), not a
    substitute for it.
    """
    if email_message.service_request_id is None:
        raise ValueError(
            f"EmailMessage {email_message.id} is not matched to a ServiceRequest yet; "
            f"run matching before extracting documents."
        )

    documents = []
    for attachment in attachments:
        document = document_services.upload_document(
            service_request=email_message.service_request,
            file=attachment["file"],
            original_filename=attachment["filename"],
            uploaded_by_type=Document.UploadedByType.SYSTEM,
            source_email=email_message,
        )
        documents.append(document)

    email_message.status = EmailMessage.Status.PROCESSED
    email_message.save(update_fields=["status"])
    return documents
