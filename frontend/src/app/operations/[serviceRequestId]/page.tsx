import Link from "next/link";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { ServiceRequestTabs } from "@/components/service-requests/ServiceRequestTabs";
import { StatusBadge } from "@/components/service-requests/StatusBadge";
import { apiFetch } from "@/lib/api/client";
import type { ChecklistItem } from "@/types/checklist";
import type { ServiceRequestDetail } from "@/types/service-request";
import type { TimelineEntry } from "@/types/timeline";
import type { WorkflowStepInstance } from "@/types/workflow";

// See the identical directive in ../page.tsx for why this is required,
// not redundant, despite the fetch layer already using no-store.
export const dynamic = "force-dynamic";

interface ServiceRequestDetailPageProps {
  params: Promise<{ serviceRequestId: string }>;
}

/**
 * Real detail page from GET /api/service-requests/{id}/, plus three
 * sibling fetches for the tabs that DO have safe, genuinely-filterable
 * backend support (Activity via the timeline endpoint, Checklist and
 * Workflow via their real `?service_request=` query param — verified in
 * backend/checklists/views.py and backend/workflow/views.py). Documents
 * is deliberately NOT fetched here: DocumentViewSet has no such filter,
 * so there is no safe way to load only this case's documents — see the
 * Documents tab's own "not connected" state instead of guessing.
 */
export default async function ServiceRequestDetailPage({ params }: ServiceRequestDetailPageProps) {
  const { serviceRequestId } = await params;

  const detailResult = await apiFetch<ServiceRequestDetail>(`service-requests/${serviceRequestId}/`);

  if (!detailResult.ok) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Link href="/operations" className="text-sm text-zinc-500 hover:underline">
          ← Operations
        </Link>
        <ApiErrorState result={detailResult} />
      </div>
    );
  }

  const [timelineResult, checklistResult, workflowResult] = await Promise.all([
    apiFetch<TimelineEntry[]>(`service-requests/${serviceRequestId}/timeline/`),
    apiFetch<ChecklistItem[]>(`checklist-items/?service_request=${serviceRequestId}`),
    apiFetch<WorkflowStepInstance[]>(`workflow-steps/?service_request=${serviceRequestId}`),
  ]);

  const serviceRequest = detailResult.data;

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="border-b border-black/[.08] pb-4">
        <p className="text-xs text-zinc-500">
          <Link href="/operations" className="hover:underline">
            Operations
          </Link>{" "}
          / {serviceRequest.reference_code}
        </p>
        <div className="mt-1 flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
            {serviceRequest.reference_code}
          </h1>
          <StatusBadge status={serviceRequest.status} />
        </div>
      </header>

      <ServiceRequestTabs
        detail={serviceRequest}
        timeline={timelineResult}
        checklist={checklistResult}
        workflow={workflowResult}
      />
    </div>
  );
}
