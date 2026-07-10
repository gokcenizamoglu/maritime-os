"""
The checklist domain's event handlers.

This is the other half of the decoupling described in
`documents/services.py`: rather than that module calling
`recompute_checklist_item()` directly, it emits an event, and THIS
module — owned by the checklist domain, imported only from
`events/bootstrap.py` — decides what checklist-side consequence follows.

Registered here, not in documents/, on purpose: the checklist domain
should own the decision "when a document is (re)classified or
superseded, which checklist items need recomputing", not have that
decision live inside the document domain's code.
"""
from checklists.services import recompute_checklist_item
from events.dispatcher import on
from events.types import DOCUMENT_CLASSIFIED, DOCUMENT_SUPERSEDED


@on(DOCUMENT_CLASSIFIED)
def _recompute_checklist_items_on_classification(event):
    previous_item = event.payload.get("previous_checklist_item")
    new_item = event.payload.get("new_checklist_item")

    if previous_item and (new_item is None or previous_item.pk != new_item.pk):
        recompute_checklist_item(previous_item)
    if new_item:
        recompute_checklist_item(new_item)


@on(DOCUMENT_SUPERSEDED)
def _recompute_checklist_items_on_supersede(event):
    old_item = event.payload.get("old_checklist_item")
    new_item = event.payload.get("new_checklist_item")

    if old_item:
        recompute_checklist_item(old_item)
    if new_item and (old_item is None or new_item.pk != old_item.pk):
        recompute_checklist_item(new_item)
