/**
 * Matches `activity.services.build_timeline_entry()` exactly, verified
 * against a real response from GET /api/service-requests/{id}/timeline/
 * (backend/activity/views.py::ServiceRequestTimelineView).
 */
export interface TimelineEntryActor {
  type: string;
  id: number | null;
  name: string | null;
}

export interface TimelineEntryContext {
  service_request_id: number;
  entity_type: string;
  entity_id: string;
}

export interface TimelineEntry {
  id: number;
  verb: string;
  summary: string;
  actor: TimelineEntryActor;
  timestamp: string;
  context: TimelineEntryContext;
  metadata: Record<string, unknown>;
}
