from activity.models import ActivityLog


def log_activity(*, tenant, verb: str, entity_type: str, entity_id, service_request=None,
                   actor_type: str, actor_user=None, summary: str = "", metadata: dict | None = None) -> ActivityLog:
    """
    The ONLY function that should ever create an ActivityLog row.
    Centralizing this means every other service function calls one
    consistent API instead of each inventing its own logging shape.

    `summary` (new): a short, human-readable, already-formatted sentence
    ("Passport uploaded by customer", "Reclassified from Bill of Sale to
    Incumbency Certificate"). Stored inside `metadata["summary"]` rather
    than as its own column — it's presentation data, not something
    queried/filtered on, so it doesn't need a dedicated indexed field.
    Callers that don't build one (yet) can omit it; `to_timeline_entry()`
    below falls back to a generic "<verb> on <entity_type>" string, so
    older/rare events still render something reasonable in a future UI.
    """
    metadata = dict(metadata or {})
    if summary:
        metadata["summary"] = summary
    return ActivityLog.objects.create(
        tenant=tenant,
        service_request=service_request,
        actor_type=actor_type,
        actor_user=actor_user,
        verb=verb,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata=metadata,
    )


def build_timeline_entry(log: ActivityLog) -> dict:
    """
    ARCHITECTURAL ADDITION (Activity Log -> Timeline System): the raw
    `ActivityLog` row is storage-shaped (flat verb/entity_type/entity_id
    strings, a JSON blob), not UI-shaped. This function is the single
    place that turns one into the other, so a future timeline endpoint
    is a thin serializer around this rather than reinventing the
    shaping logic per-endpoint.

    Returns a plain dict (not tied to DRF) so it's usable from a
    management command, a test, or a future non-DRF surface too.
    """
    actor_name = None
    if log.actor_user_id:
        actor_name = getattr(log.actor_user, "get_full_name", lambda: None)() or log.actor_user.username

    return {
        "id": log.id,
        "verb": log.verb,
        "summary": log.metadata.get("summary") or f"{log.verb.replace('_', ' ').replace('.', ' ')}",
        "actor": {
            "type": log.actor_type,
            "id": log.actor_user_id,
            "name": actor_name,
        },
        "timestamp": log.created_at.isoformat(),
        "context": {
            "service_request_id": log.service_request_id,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
        },
        "metadata": {k: v for k, v in log.metadata.items() if k != "summary"},
    }
