import Link from "next/link";
import type { ServiceRequestOrderingField, ServiceRequestStatus } from "@/types/service-request";

/**
 * Only `status`, `search`, and `ordering` get interactive controls here
 * — the complete set of filters this frontend currently exposes. The
 * backend ALSO supports `customer`/`vessel`/`service_type`/`flag` (see
 * backend/service_requests/views.py::ServiceRequestViewSet
 * .filterset_fields), but those are deliberately NOT wired up here and
 * NOT forwarded from the URL at all (see the query whitelist in
 * app/operations/page.tsx): the list response only ever returns
 * `customer_name`/`vessel_name`/etc. as flat strings, never an id, and
 * no Customers/Vessels/Catalog list endpoint exists yet to resolve one
 * by. Building a picker here would mean inventing ids to populate it
 * with. See docs/FRONTEND_INFORMATION_ARCHITECTURE.md for the full
 * backend-supported / frontend-exposed / deferred breakdown.
 */
const STATUS_OPTIONS: { value: ServiceRequestStatus; label: string }[] = [
  { value: "draft", label: "Draft" },
  { value: "collecting_documents", label: "Collecting Documents" },
  { value: "ready", label: "Ready" },
  { value: "in_progress", label: "In Progress" },
  { value: "waiting_external", label: "Waiting External" },
  { value: "completed", label: "Completed" },
];

const ORDERING_OPTIONS: { value: `-${ServiceRequestOrderingField}` | ServiceRequestOrderingField; label: string }[] = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-updated_at", label: "Recently updated" },
  { value: "reference_code", label: "Reference (A–Z)" },
  { value: "-reference_code", label: "Reference (Z–A)" },
  { value: "status", label: "Status" },
];

const controlClasses =
  "h-9 rounded-md border border-black/[.12] px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";

interface OperationsFiltersProps {
  status?: string;
  search?: string;
  ordering?: string;
}

/**
 * A plain GET `<form>` — submitting it navigates to
 * `/operations?status=...&search=...&ordering=...`, which the Server
 * Component page already reads via `searchParams`. No client JS, no
 * "use client", no state library needed for this.
 *
 * Changing a filter deliberately has no hidden `page` field, so
 * submitting always lands on page 1 of the new result set rather than
 * risking an out-of-range page against a smaller filtered count.
 */
export function OperationsFilters({ status, search, ordering }: OperationsFiltersProps) {
  const hasActiveFilters = Boolean(status || search || ordering);

  return (
    <form method="GET" action="/operations" className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor="search" className="text-xs font-medium text-zinc-500">
          Search
        </label>
        <input
          id="search"
          name="search"
          type="search"
          defaultValue={search ?? ""}
          placeholder="Reference, customer, vessel..."
          className={`${controlClasses} w-64`}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="status" className="text-xs font-medium text-zinc-500">
          Status
        </label>
        <select id="status" name="status" defaultValue={status ?? ""} className={controlClasses}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="ordering" className="text-xs font-medium text-zinc-500">
          Sort by
        </label>
        <select id="ordering" name="ordering" defaultValue={ordering ?? "-created_at"} className={controlClasses}>
          {ORDERING_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        className="h-9 rounded-md bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
      >
        Apply
      </button>

      {hasActiveFilters && (
        <Link
          href="/operations"
          className="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 hover:text-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
        >
          Clear
        </Link>
      )}
    </form>
  );
}
