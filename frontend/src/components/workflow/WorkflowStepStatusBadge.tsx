import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { WorkflowStepStatus } from "@/types/workflow";

/** Verified against WorkflowStepInstance.Status in backend/workflow/models.py. */
const STATUS: Record<WorkflowStepStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: "Pending", tone: "neutral" },
  active: { label: "Active", tone: "info" },
  blocked: { label: "Blocked", tone: "warning" },
  waiting_external: { label: "Waiting External", tone: "warning" },
  completed: { label: "Completed", tone: "success" },
  skipped: { label: "Skipped", tone: "neutral" },
};

export function WorkflowStepStatusBadge({ status }: { status: WorkflowStepStatus }) {
  const config = STATUS[status];
  return <Badge tone={config.tone}>{config.label}</Badge>;
}
