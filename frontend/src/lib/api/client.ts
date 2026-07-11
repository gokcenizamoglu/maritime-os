/**
 * Minimal typed fetch layer over the backend API, built on `buildApiUrl`
 * (see ./config.ts). Extends, not replaces, that file — config.ts still
 * owns "where is the API"; this file owns "how do we call it and
 * represent what came back."
 *
 * WHY A DISCRIMINATED RESULT INSTEAD OF THROWING: every consumer of this
 * (list page, detail page, each tab) needs to render a SPECIFIC state —
 * loading, empty, error, unauthorized, misconfigured — not just "it broke."
 * A thrown exception forces every call site to reconstruct that
 * information from a caught error; returning `ApiResult<T>` makes the
 * caller pattern-match on `.ok`/`.kind` directly. See
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md for which states this
 * intentionally distinguishes and why.
 *
 * SERVER-SIDE ONLY (for now): every current caller is a Next.js Server
 * Component, so this fetch runs in Node, not the browser — it is NOT
 * subject to the browser's CORS policy. It also does not attach any
 * browser session cookie, because there is no login flow yet for one to
 * exist. See the Stage 5 findings referenced in the project's frontend
 * implementation report for the full explanation — this file does not
 * paper over that; unauthenticated requests correctly surface as
 * `{ kind: "unauthorized" }` below, exactly as the backend reports them.
 */
import { buildApiUrl } from "./config";
import type { ApiDetailError, ApiError } from "@/types/api";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; kind: "config_error"; message: string }
  | { ok: false; kind: "network_error"; message: string }
  | { ok: false; kind: "unauthorized"; status: 401 | 403; error: ApiError | null }
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

/**
 * Fetches `path` (relative to the API base — see buildApiUrl) and parses
 * the JSON body into `T`. Never throws for expected failure modes
 * (missing config, network failure, 4xx/5xx) — those become a typed
 * `ApiResult`. `cache: "no-store"` is deliberate: this is live operational
 * data, and it also tells Next.js these routes must render dynamically,
 * not be prerendered at build time against a backend that may not be
 * running during `next build`.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let url: string;
  try {
    url = buildApiUrl(path);
  } catch (err) {
    return { ok: false, kind: "config_error", message: err instanceof Error ? err.message : String(err) };
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (err) {
    return { ok: false, kind: "network_error", message: err instanceof Error ? err.message : String(err) };
  }

  if (response.status === 401 || response.status === 403) {
    const error = await safeJson<ApiError>(response);
    return { ok: false, kind: "unauthorized", status: response.status, error };
  }

  if (!response.ok) {
    const error = await safeJson<ApiError>(response);
    return { ok: false, kind: "http_error", status: response.status, error };
  }

  const data = await safeJson<T>(response);
  if (data === null) {
    // 2xx status but an unparseable body — treat as a distinct failure
    // rather than letting response.json() throw uncaught here, which
    // would skip every ApiErrorState branch above and fall through to
    // Next.js's generic unstyled error boundary instead.
    return { ok: false, kind: "parse_error", status: response.status };
  }
  return { ok: true, data };
}

async function safeJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
