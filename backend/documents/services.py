"""
Service layer for the document domain.

ARCHITECTURAL CHANGE (domain decoupling): this module previously
imported `checklists.services.recompute_checklist_item` and
`activity.services.log_activity` directly — meaning the document
domain's code had to know about checklist internals and logging
mechanics. It no longer imports either. Every state-changing operation
here now ends by calling `events.dispatcher.emit(...)`; checklist
recompute and activity logging happen in `checklists/listeners.py` and
`activity/listeners.py` respectively, entirely outside this file.

This is what "prepare for AI integration" concretely means at the code
level: a future AI classifier calling `classify_document()` (to CONFIRM
a prediction) gets the exact same checklist/logging side effects for
free, with this module never needing to change, and never needing to
import anything AI-related.
"""
from django.db import transaction
from documents.models import Document
from events.dispatcher import emit
from events.types import DOCUMENT_CLASSIFIED, DOCUMENT_SUPERSEDED, DOCUMENT_UPLOADED
from service_requests.models import ServiceRequest


def upload_document(*, service_request: ServiceRequest, file, original_filename: str,
                     uploaded_by_type: str, uploaded_by_user=None, source_email=None) -> Document:
    """
    Record a raw, unstructured upload. document_type is intentionally
    left null — classification is a separate, later step performed by
    an internal user (Phase 1), an AI classifier, or email ingestion
    (Phase 2 — see `source_email`, wired now so Document doesn't need a
    migration when email ingestion actually lands).
    """
    document = Document.objects.create(
        tenant=service_request.tenant,
        service_request=service_request,
        file=file,
        original_filename=original_filename,
        uploaded_by_type=uploaded_by_type,
        uploaded_by_user=uploaded_by_user,
        source_email=source_email,
        status=Document.Status.UNCLASSIFIED,
    )
    emit(
        DOCUMENT_UPLOADED,
        document=document,
        service_request=service_request,
        actor_type=uploaded_by_type,
        actor_user=uploaded_by_user,
    )
    return document


@transaction.atomic
def classify_document(*, document: Document, document_type, actor_user, mark_validated: bool = False) -> Document:
    """
    Map an unstructured Document to a DocumentType (the "Tarik" manual
    mapping action), or RE-classify one that was already mapped to a
    different type.

    Reclassification safety (unchanged from the hardening pass, now
    expressed via the event payload instead of a direct function call):
    the PREVIOUS checklist_item is captured before reassignment and
    included in the emitted event, so the listener can recompute both
    the item being vacated and the item being filled. This is what
    "reclassification remains safe" means concretely — the safety
    property doesn't depend on this function remembering to call a
    specific checklist function; it depends on the event carrying
    enough information for ANY listener to do the right thing, now or
    after future listeners are added.
    """
    previous_checklist_item = document.checklist_item
    previous_document_type = document.document_type

    document.document_type = document_type
    document.status = Document.Status.VALIDATED if mark_validated else Document.Status.CLASSIFIED

    # Import here (not at module level) specifically to avoid document
    # <-> checklist import coupling at load time; ChecklistItem is read
    # data here, not a cross-domain service call, so this is a narrower
    # exception than the removed `checklists.services` import.
    from checklists.models import ChecklistItem
    new_checklist_item = ChecklistItem.objects.filter(
        service_request=document.service_request, document_type=document_type,
    ).first()
    document.checklist_item = new_checklist_item

    document.save(update_fields=["document_type", "status", "checklist_item", "updated_at"])

    emit(
        DOCUMENT_CLASSIFIED,
        document=document,
        service_request=document.service_request,
        previous_document_type=previous_document_type,
        previous_checklist_item=previous_checklist_item,
        new_checklist_item=new_checklist_item,
        actor_user=actor_user,
        actor_type="user" if actor_user else "system",
    )
    return document


@transaction.atomic
def supersede_document(*, old_document: Document, new_file, original_filename: str,
                        uploaded_by_type: str, uploaded_by_user=None) -> Document:
    """
    Replace a document with a corrected version without losing history.
    The new document inherits the classification of the old one if it
    had one; the emitted event carries both checklist_item references so
    the listener can recompute whichever items are actually affected.
    """
    new_document = Document.objects.create(
        tenant=old_document.tenant,
        service_request=old_document.service_request,
        document_type=old_document.document_type,
        checklist_item=old_document.checklist_item,
        file=new_file,
        original_filename=original_filename,
        uploaded_by_type=uploaded_by_type,
        uploaded_by_user=uploaded_by_user,
        status=Document.Status.UNCLASSIFIED if not old_document.document_type else old_document.status,
        supersedes=old_document,
    )
    emit(
        DOCUMENT_SUPERSEDED,
        old_document=old_document,
        new_document=new_document,
        service_request=old_document.service_request,
        old_checklist_item=old_document.checklist_item,
        new_checklist_item=new_document.checklist_item,
        actor_type=uploaded_by_type,
        actor_user=uploaded_by_user,
    )
    return new_document
