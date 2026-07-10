"""
A deliberately small, synchronous domain event system.

WHY THIS EXISTS (architectural gap this closes):
Before this, `documents.services` imported `checklists.services` imported
`activity.services` directly — three domains hard-wired together by
import statements. That works fine at Phase 1 scale, but it means every
new consequence of "a document was classified" (recompute a checklist,
write an audit log, and soon: notify a customer, trigger AI re-scoring,
kick off an email reply) has to be added as ANOTHER direct call inside
`classify_document()`, which just accumulates unrelated responsibilities
in one function forever.

Domain events invert that: a service function's job is to change ITS
OWN domain's state and then announce "this happened" — `emit(...)`.
Anyone downstream (checklists, activity, tomorrow's automation engine)
subscribes to that announcement without the emitting domain needing to
know or care who's listening. `documents/services.py` no longer imports
`checklists.services` or `activity.services` at all.

WHY SYNCHRONOUS FOR NOW (per explicit instruction not to build async
infra yet): `emit()` calls every registered handler in-process, in the
same request/transaction, in registration order. This is intentional —
it keeps behavior fully deterministic and debuggable while the event
vocabulary stabilizes. The migration path to Celery/an event bus later
is a ONE-LINE change inside `emit()` (dispatch via `.delay()` instead of
calling directly) — no call site anywhere in the codebase needs to
change, because they only ever call `emit()`, never a handler directly.

Handlers run inside whatever transaction the emitting service is in
(services already wrap their mutations in `@transaction.atomic`), so a
handler raising an exception rolls back the whole operation — this is
correct behavior for now (e.g. if checklist recompute fails, the
classification that triggered it should not silently "succeed" from the
document's point of view). Revisit if/when a handler needs to be
best-effort (e.g. a notification that shouldn't block the write path).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from django.utils import timezone


@dataclass(frozen=True)
class DomainEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=timezone.now)


_REGISTRY: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(list)


def on(event_name: str):
    """Decorator: register a handler for an event name. Handlers should
    live in the CONSUMING domain's `listeners.py`, not the emitting one."""
    def decorator(handler: Callable[[DomainEvent], None]):
        _REGISTRY[event_name].append(handler)
        return handler
    return decorator


def emit(event_name: str, **payload) -> DomainEvent:
    """Announce that something happened. Fan-out to every registered
    handler, synchronously, in registration order."""
    event = DomainEvent(name=event_name, payload=payload)
    for handler in _REGISTRY[event_name]:
        handler(event)
    return event


def clear_registry_for_tests() -> None:
    """Test-only helper — avoids handler leakage across test cases that
    re-import listener modules."""
    _REGISTRY.clear()
