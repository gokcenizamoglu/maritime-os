import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { ServiceRequestStatus } from "@/types/service-request";

/** Matches docs/DESIGN_SYSTEM.md §10 — verified against ServiceRequest.Status. */
const STATUS: Record<ServiceRequestStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft", tone: "neutral" },
  collecting_documents: { label: "Collecting Documents", tone: "neutral" },
  ready: { label: "Ready", tone: "info" },
  in_progress: { label: "In Progress", tone: "info" },
  waiting_external: { label: "Waiting External", tone: "warning" },
  completed: { label: "Completed", tone: "success" },
};

export function StatusBadge({ status }: { status: ServiceRequestStatus }) {
  const config = STATUS[status];
  return <Badge tone={config.tone}>{config.label}</Badge>;
}
