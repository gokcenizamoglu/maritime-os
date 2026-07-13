/**
 * Shared API-facing types, framework-agnostic. This mirrors the actual
 * shapes the Django REST Framework backend returns (see
 * backend/config/permissions.py and DRF's default exception handling /
 * pagination), so feature code has one shared place to import them from
 * instead of redefining them per call site.
 */

/** DRF's default validation-error shape: field name -> list of messages. */
export type ApiFieldErrors = Record<string, string[]>;

/** DRF's shape for non-field errors, e.g. permission denials. */
export interface ApiDetailError {
  detail: string;
}

export type ApiError = ApiFieldErrors | ApiDetailError;

/**
 * DRF's `PageNumberPagination` envelope — matches
 * backend/config/pagination.py::StandardResultsPagination exactly
 * (verified against a real response, not assumed). Currently applied to
 * ServiceRequest and Document list endpoints only; NOT checklist-items
 * or workflow-steps, which still return a plain array — see
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md for which endpoints are
 * paginated and why not all of them are.
 */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
