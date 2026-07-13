/**
 * Server-only typed fetch layer over the backend API, built on
 * `buildApiUrl` (./config.ts) and `ApiResult` (./result.ts — imported
 * from there, not redefined here, and re-exported below for existing
 * call sites). config.ts owns "where is the API"; result.ts owns "how
 * do we represent what came back"; this file owns "how do we actually
 * call it," including the auth relay.
 *
 * SERVER-ONLY, NOW LOAD-BEARING: this file reads the Next.js-origin
 * session/CSRF relay cookies (lib/auth/session.ts, which uses
 * `next/headers`) and forwards them to Django as real `Cookie` /
 * `X-CSRFToken` headers — the browser never sends these to Django
 * directly, only Next's server does, here. `next/headers` cannot be
 * bundled into a Client Component, so nothing in this file may be
 * imported from one; see result.ts's docstring for the concrete build
 * failure this caused before `ApiResult`/`describeApiError` were split
 * out into their own dependency-free module. This also runs entirely
 * server-to-server, so it is NOT subject to the browser's CORS policy.
 */
import { DJANGO_CSRF_HEADER_NAME, DJANGO_SESSION_COOKIE_NAME } from "@/lib/auth/backend-auth";
import { getCsrfRelay, getSessionRelay } from "@/lib/auth/session";
import type { ApiError } from "@/types/api";
import { buildApiUrl } from "./config";
import type { ApiResult } from "./result";

export type { ApiResult } from "./result";
export { describeApiError } from "./result";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * Fetches `path` (relative to the API base — see buildApiUrl) and parses
 * the JSON body into `T`. Never throws for expected failure modes
 * (missing config, network failure, 4xx/5xx) — those become a typed
 * `ApiResult`. `cache: "no-store"` is deliberate: this is live
 * per-request, request-authenticated data, and it tells Next.js these
 * routes must render dynamically.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let url: string;
  try {
    url = buildApiUrl(path);
  } catch (err) {
    return { ok: false, kind: "config_error", message: err instanceof Error ? err.message : String(err) };
  }

  const method = (init?.method ?? "GET").toUpperCase();
  const sessionRelay = await getSessionRelay();
  const hadRelay = Boolean(sessionRelay);

  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (sessionRelay) {
    headers.set("Cookie", `${DJANGO_SESSION_COOKIE_NAME}=${sessionRelay}`);
  }
  if (!SAFE_METHODS.has(method)) {
    const csrfRelay = await getCsrfRelay();
    if (csrfRelay) {
      headers.set(DJANGO_CSRF_HEADER_NAME, csrfRelay);
    }
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, method, cache: "no-store", headers });
  } catch (err) {
    return { ok: false, kind: "network_error", message: err instanceof Error ? err.message : String(err) };
  }

  if (response.status === 401) {
    const error = await safeJson<ApiError>(response);
    return { ok: false, kind: "unauthenticated", error };
  }

  if (response.status === 403) {
    const rawText = await response.text();
    const parsed = parseJsonSafely<ApiError>(rawText);
    if (parsed === null) {
      // Non-JSON 403 body -> Django's own CSRF rejection page, not a
      // DRF permission error.
      return { ok: false, kind: "csrf_failure" };
    }
    return hadRelay
      ? { ok: false, kind: "forbidden", error: parsed }
      : { ok: false, kind: "unauthenticated", error: parsed };
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

function parseJsonSafely<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}
