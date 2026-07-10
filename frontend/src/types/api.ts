/**
 * Shared API-facing types. Kept minimal and framework-agnostic — no
 * per-endpoint response shapes yet, since no feature calls the backend
 * from this initial shell. This mirrors the two error shapes the
 * Django REST Framework backend actually returns (see
 * backend/config/permissions.py and DRF's default exception handling),
 * so future feature code has one shared place to import them from
 * instead of redefining them per call site.
 */

/** DRF's default validation-error shape: field name -> list of messages. */
export type ApiFieldErrors = Record<string, string[]>;

/** DRF's shape for non-field errors, e.g. permission denials. */
export interface ApiDetailError {
  detail: string;
}

export type ApiError = ApiFieldErrors | ApiDetailError;
