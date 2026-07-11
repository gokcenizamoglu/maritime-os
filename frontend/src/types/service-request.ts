/**
 * Types match `backend/service_requests/serializers.py` exactly, verified
 * against real JSON returned by a running instance (not inferred from
 * field names alone) — see docs/FRONTEND_INFORMATION_ARCHITECTURE.md §4/§6
 * for the verification method.
 *
 * IMPORTANT ASYMMETRY, not a typo: `ServiceRequestListSerializer` exposes
 * human-readable `*_name` strings, but `ServiceRequestDetailSerializer`
 * exposes `customer`/`vessel`/`service_type`/`flag` as PLAIN INTEGER IDs
 * (DRF's default PrimaryKeyRelatedField, since the detail serializer never
 * overrides those fields with a `source="...name"` CharField the way the
 * list serializer does). This is a real backend limitation, not a
 * frontend bug — do not "fix" it here by guessing names.
 */

/** Matches `ServiceRequest.Status` in backend/service_requests/models.py. */
export type ServiceRequestStatus =
  | "draft"
  | "collecting_documents"
  | "ready"
  | "in_progress"
  | "waiting_external"
  | "completed";

/** GET /api/service-requests/ — one array item. */
export interface ServiceRequestListItem {
  id: number;
  reference_code: string;
  status: ServiceRequestStatus;
  vessel_name: string;
  customer_name: string;
  service_type_name: string;
  flag_name: string;
  created_at: string;
}

export interface ChecklistProgress {
  total: number;
  complete: number;
  percent: number;
}

/** GET /api/service-requests/{id}/ */
export interface ServiceRequestDetail {
  id: number;
  reference_code: string;
  status: ServiceRequestStatus;
  /** Raw FK id — see module docstring. Not a display name. */
  customer: number;
  /** Raw FK id — see module docstring. Not a display name. */
  vessel: number;
  /** Raw FK id — see module docstring. Not a display name. */
  service_type: number;
  /** Raw FK id — see module docstring. Not a display name. */
  flag: number;
  created_at: string;
  updated_at: string;
  checklist_progress: ChecklistProgress;
}
