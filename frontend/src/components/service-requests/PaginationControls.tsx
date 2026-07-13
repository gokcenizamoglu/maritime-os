import Link from "next/link";

/**
 * Display-math only, mirroring backend/config/pagination.py::
 * StandardResultsPagination.page_size — used ONLY to compute the
 * "Showing X–Y of Z" range shown here. The backend remains the sole
 * authority on the actual page size applied; this constant is never
 * sent to or validated against the API.
 */
const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 100;

function buildPageHref(query: URLSearchParams, page: number): string {
  const nextQuery = new URLSearchParams(query);
  if (page > 1) {
    nextQuery.set("page", String(page));
  } else {
    nextQuery.delete("page");
  }
  const queryString = nextQuery.toString();
  return queryString ? `/operations?${queryString}` : "/operations";
}

interface PaginationControlsProps {
  /**
   * The SAME sanitized query built by app/operations/page.tsx — reusing
   * it (rather than each component whitelisting params separately) is
   * what guarantees a Previous/Next link can never carry a param the
   * page itself wouldn't also forward to the backend.
   */
  query: URLSearchParams;
  resultCount: number;
  totalCount: number;
  hasNext: boolean;
  hasPrevious: boolean;
}

export function PaginationControls({ query, resultCount, totalCount, hasNext, hasPrevious }: PaginationControlsProps) {
  const page = query.get("page") ? Number(query.get("page")) : 1;
  const requestedPageSize = query.get("page_size") ? Number(query.get("page_size")) : NaN;
  const pageSize = requestedPageSize > 0 ? Math.min(requestedPageSize, MAX_PAGE_SIZE) : DEFAULT_PAGE_SIZE;
  const rangeStart = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = rangeStart + resultCount - 1;

  const linkClasses =
    "rounded-md border border-black/[.12] px-3 py-1.5 text-sm hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900";
  const disabledClasses = "rounded-md border border-black/[.08] px-3 py-1.5 text-sm text-zinc-300";

  return (
    <div className="flex items-center justify-between border-t border-black/[.08] pt-3 text-sm text-zinc-600">
      <span>
        Showing {rangeStart}–{rangeEnd} of {totalCount}
      </span>
      <div className="flex gap-2">
        {hasPrevious ? (
          <Link href={buildPageHref(query, page - 1)} className={linkClasses}>
            Previous
          </Link>
        ) : (
          <span className={disabledClasses}>Previous</span>
        )}
        {hasNext ? (
          <Link href={buildPageHref(query, page + 1)} className={linkClasses}>
            Next
          </Link>
        ) : (
          <span className={disabledClasses}>Next</span>
        )}
      </div>
    </div>
  );
}
