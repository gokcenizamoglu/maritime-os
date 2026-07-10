"""
Email ingestion skeleton — Phase 2 PREPARATION ONLY.

Per explicit instruction, this does NOT implement a working email
ingestion system (no IMAP/Graph API client, no parsing, no scheduler).
What it DOES do is answer the two structural questions that are
expensive to retrofit later:

  1. WHERE does an ingested email attach to a ServiceRequest?
     -> EmailMessage model below, with a nullable `service_request` FK —
        nullable because an ingested email often can't be matched to a
        case until AFTER some matching logic runs (by reference code in
        the subject, by sender address, by manual triage), so
        "unmatched inbox" has to be a valid, representable state.

  2. WHAT service call does the actual ingestion pipeline invoke once
     it has parsed a message?
     -> `ingest_email()` and `extract_documents_from_email()` below,
        which reuse the EXISTING `documents.services.upload_document()`
        so attachments become normal Documents indistinguishable from a
        portal upload, tagged via `source_email` for traceability.

This means Phase 2's actual email worker is an ADAPTER that calls these
two functions — it does not require touching ServiceRequest, Document,
or Checklist code at all.
"""
from config.base_models import TenantScopedModel
from django.db import models


class EmailMessage(TenantScopedModel):
    """A single ingested email, before or after being matched to a case."""
    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        MATCHED = "matched", "Matched to ServiceRequest"
        PROCESSED = "processed", "Attachments Extracted"
        IGNORED = "ignored", "Ignored (not case-relevant)"

    service_request = models.ForeignKey(
        "service_requests.ServiceRequest", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="emails",
    )
    external_message_id = models.CharField(
        max_length=255, unique=True,
        help_text="The mail provider's Message-ID header — used to prevent "
                   "re-ingesting the same email twice.",
    )
    from_address = models.EmailField()
    subject = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField()
    raw_body_storage_key = models.CharField(
        max_length=500,
        help_text="Pointer into the same S3-compatible storage documents use — "
                   "the raw email body/EML is stored as a blob, not in the DB.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED)

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self):
        return f"{self.subject} ({self.from_address})"
