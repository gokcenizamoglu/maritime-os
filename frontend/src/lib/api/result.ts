/**
 * `ApiResult<T>` and its pure helpers, split out of client.ts
 * DELIBERATELY: apiFetch (client.ts) now reads the auth relay via
 * `next/headers` (lib/auth/session.ts), which Next.js refuses to bundle
 * into any Client Component's code — but `ApiResult` and
 * `describeApiError` are pure data/formatting with no such dependency,
 * and `ApiErrorState` (a component rendered from inside the
 * Client-Component `ServiceRequestTabs`) needs them. Importing from
 * client.ts directly would drag its server-only dependency chain into
 * client bundles and fail the build — confirmed by an actual Turbopack
 * build error while wiring up the auth relay, not a hypothetical.
 * Import from HERE, not client.ts, in anything that isn't itself
 * doing the actual fetch.
 */
import type { ApiDetailError, ApiError } from "@/types/api";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; kind: "config_error"; message: string }
  | { ok: false; kind: "network_error"; message: string }
  /** No valid credential was ever presented — status 401, or a 403 with no session relay cookie at all. The caller should clear any stale relay and route to /login. */
  | { ok: false; kind: "unauthenticated"; error: ApiError | null }
  /**
   * A session relay WAS sent, but Django rejected the request anyway —
   * status 403 with a normal (JSON) DRF error body. NOTE: DRF's default
   * exception handling does not distinguish "your session is invalid/
   * expired" from "you're authenticated but not permitted here" at the
   * HTTP level in this project's current configuration (verified
   * empirically — both surface as 403 with a `{"detail": "..."}` body).
   * Callers should generally treat this the same as `unauthenticated`
   * (offer re-login) until the backend grows a permission model that
   * actually needs the distinction — see
   * docs/AUTHENTICATION_ARCHITECTURE.md.
   */
  | { ok: false; kind: "forbidden"; error: ApiError | null }
  /**
   * A 403 whose body is NOT valid JSON — Django's own CSRF-rejection
   * page (`django.views.csrf.csrf_failure`), returned directly by
   * `CsrfViewMiddleware`/`csrf_protect` without ever reaching DRF's JSON
   * exception handling. Confirmed empirically while building the login
   * flow: every other 403 in this codebase returns valid JSON; only a
   * CSRF failure returns HTML. Reused as the reliable signal here.
   */
  | { ok: false; kind: "csrf_failure" }
  | { ok: false; kind: "http_error"; status: number; error: ApiError | null }
  | { ok: false; kind: "parse_error"; status: number };

function isDetailError(error: ApiError): error is ApiDetailError {
  return typeof error === "object" && error !== null && "detail" in error;
}

/** Extracts a human-readable message from a DRF error body, if present. */
export function describeApiError(error: ApiError | null): string | null {
  if (!error) return null;
  if (isDetailError(error)) return error.detail;
  const messages = Object.entries(error).map(([field, msgs]) => `${field}: ${msgs.join(", ")}`);
  return messages.length > 0 ? messages.join("; ") : null;
}
