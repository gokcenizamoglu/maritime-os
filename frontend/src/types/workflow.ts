/**
 * Matches `workflow/serializers.py::WorkflowStepInstanceSerializer` and
 * `WorkflowStepInstance.Status` in backend/workflow/models.py exactly.
 * `GET /api/workflow-steps/?service_request={id}` — the query param IS
 * genuinely implemented server-side (backend/workflow/views.py::
 * WorkflowStepInstanceViewSet.get_queryset).
 */
export type WorkflowStepStatus =
  | "pending"
  | "active"
  | "blocked"
  | "waiting_external"
  | "completed"
  | "skipped";

export interface WorkflowStepInstance {
  id: number;
  step_code: string;
  step_name: string;
  status: WorkflowStepStatus;
  is_external: boolean;
  /** Raw FK id (Organization), or null. Not a display name. */
  assigned_organization: number | null;
  started_at: string | null;
  completed_at: string | null;
  depends_on_codes: string[];
}
