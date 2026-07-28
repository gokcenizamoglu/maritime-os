import Link from "next/link";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { OperationsFilters } from "@/components/service-requests/OperationsFilters";
import { PaginationControls } from "@/components/service-requests/PaginationControls";
import { ServiceRequestTable } from "@/components/service-requests/ServiceRequestTable";
import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "@/types/api";
import type { AuthenticatedUser } from "@/types/auth";
import type { ServiceRequestListItem, ServiceRequestStatus } from "@/types/service-request";

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
 * The ONLY query params this frontend reads from the URL and forwards
 * to GET /api/service-requests/.
 *
 * The backend ALSO supports `customer`, `vessel`, `service_type`, and
 * `flag` (see backend/service_requests/views.py::ServiceRequestViewSet
 * .filterset_fields) — deliberately excluded here and NOT forwarded.
 * There is no Customers/Vessels/Catalog list endpoint yet to resolve a
 * display name to the id one of those filters needs, and the list
 * response only ever returns `*_name` strings, never an id — so a raw
 * `?customer=5` typed into this public URL would be an unvalidated
 * foreign-key id with no corresponding UI control and nothing on this
 * page to check it against. Forwarding it anyway would silently expose
 * backend capability this frontend cannot yet present safely. See
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md for the full
 * backend-supported / frontend-exposed / deferred breakdown.
 */
const STATUS_VALUES: readonly ServiceRequestStatus[] = [
  "draft", "collecting_documents", "ready", "in_progress", "waiting_external", "completed",
];
const ORDERING_FIELDS: readonly string[] = ["created_at", "updated_at", "reference_code", "status"];

function isPositiveIntegerString(value: string): boolean {
  return /^\d+$/.test(value) && Number(value) > 0;
}

function isValidOrdering(value: string): boolean {
  const field = value.startsWith("-") ? value.slice(1) : value;
  return ORDERING_FIELDS.includes(field);
}

type SearchParams = Record<string, string | string[] | undefined>;

interface OperationsPageProps {
  searchParams: Promise<SearchParams>;
}

function getString(params: SearchParams, key: string): string | undefined {
  const value = params[key];
  return typeof value === "string" && value !== "" ? value : undefined;
}

/**
 * Builds the exact, validated query string forwarded to the backend AND
 * used to render pagination links — a single sanitized `URLSearchParams`
 * shared by both, so a page link can never carry a param (or an invalid
 * value) the fetch itself wouldn't also send. Anything invalid (a
 * non-numeric page, an unrecognized status, an ordering field outside
 * the backend's approved list) is silently dropped rather than forwarded
 * — the goal is a clean, predictable URL, not surfacing a 400 from a
 * typo'd query param.
 */
function buildSanitizedQuery(params: SearchParams): URLSearchParams {
  const query = new URLSearchParams();

  const page = getString(params, "page");
  if (page && isPositiveIntegerString(page)) query.set("page", page);

  const pageSize = getString(params, "page_size");
  if (pageSize && isPositiveIntegerString(pageSize)) query.set("page_size", pageSize);

  const status = getString(params, "status");
  if (status && (STATUS_VALUES as readonly string[]).includes(status)) query.set("status", status);

  const search = getString(params, "search");
  if (search) query.set("search", search);

  const ordering = getString(params, "ordering");
  if (ordering && isValidOrdering(ordering)) query.set("ordering", ordering);

  return query;
}

/**
 * Real read-only, paginated list from GET /api/service-requests/.
 * Filters/search/ordering are read from the URL's query string,
 * sanitized, and forwarded to the backend — the backend does the actual
 * filtering; this page never filters client-side, which would silently
 * diverge from what the URL claims is applied. See
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md §4.
 */
export default async function OperationsPage({ searchParams }: OperationsPageProps) {
  const params = await searchParams;
  const query = buildSanitizedQuery(params);

  const queryString = query.toString();
  const path = queryString ? `service-requests/?${queryString}` : "service-requests/";

  const [result, userResult] = await Promise.all([
    apiFetch<PaginatedResponse<ServiceRequestListItem>>(path),
    apiFetch<AuthenticatedUser>("auth/me/"),
  ]);

  const canCreate = userResult.ok && userResult.data.capabilities.includes("service_request.create");

  const status = query.get("status") ?? undefined;
  const search = query.get("search") ?? undefined;
  const ordering = query.get("ordering") ?? undefined;
  const hasActiveFilters = Boolean(status || search);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between border-b border-black/[.08] pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Operations</h1>
          <p className="mt-1 text-sm text-zinc-600">All service requests across every module.</p>
        </div>
        {canCreate && (
          <Link
            href="/operations/new"
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            New Operation
          </Link>
        )}
      </div>

      <OperationsFilters status={status} search={search} ordering={ordering} />

      {!result.ok && <ApiErrorState result={result} />}

      {result.ok && result.data.count === 0 && (
        <EmptyState
          title={hasActiveFilters ? "No service requests match these filters" : "No service requests yet"}
          description={
            hasActiveFilters
              ? "Try a different search term, or clear the filters above."
              : "Service requests created in the backend will appear here."
          }
        />
      )}

      {result.ok && result.data.count > 0 && (
        <>
          <ServiceRequestTable items={result.data.results} />
          <PaginationControls
            query={query}
            resultCount={result.data.results.length}
            totalCount={result.data.count}
            hasNext={result.data.next !== null}
            hasPrevious={result.data.previous !== null}
          />
        </>
      )}
    </div>
  );
}
