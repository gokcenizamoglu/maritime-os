import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ServiceRequestTable } from "@/components/service-requests/ServiceRequestTable";
import { apiFetch } from "@/lib/api/client";
import type { ServiceRequestListItem } from "@/types/service-request";

/**
 * Forces this route to render on every request rather than being
 * prerendered once at build time. Next.js 15+ made `fetch()` uncached by
 * default, which is necessary but NOT sufficient to make a route
 * dynamic — without this, `next build` would still attempt to
 * statically generate this page once (against whatever the backend
 * returns, or an unreachable-backend error, at BUILD time) and serve
 * that same frozen result to every user forever. This is live
 * operational data; it must be fetched fresh per request.
 */
export const dynamic = "force-dynamic";

/**
 * Real read-only list from GET /api/service-requests/. No query-param
 * filters are added here: `ServiceRequestViewSet` has no `filter_backends`
 * / `filterset_fields` / `search_fields` configured (verified by reading
 * backend/service_requests/views.py) — the backend genuinely does not
 * support filtering yet, so implementing a filter UI here would imply
 * server behavior that doesn't exist. See
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md §4.
 */
export default async function OperationsPage() {
  const result = await apiFetch<ServiceRequestListItem[]>("service-requests/");

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Operations</h1>
        <p className="mt-1 text-sm text-zinc-600">All service requests across every module.</p>
      </div>

      {!result.ok && <ApiErrorState result={result} />}
      {result.ok && result.data.length === 0 && (
        <EmptyState
          title="No service requests yet"
          description="Service requests created in the backend will appear here."
        />
      )}
      {result.ok && result.data.length > 0 && <ServiceRequestTable items={result.data} />}
    </div>
  );
}
