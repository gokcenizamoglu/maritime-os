/**
 * API configuration for talking to the MaritimeOS backend.
 *
 * The base URL is read from NEXT_PUBLIC_API_BASE_URL (see
 * frontend/.env.example) — never hardcoded here, since the backend
 * origin differs between local dev, staging, and production. Referencing
 * `process.env.NEXT_PUBLIC_API_BASE_URL` as a static property access
 * (not destructured) is required for Next.js to inline it at build time.
 *
 * This file intentionally does NOT implement authentication, token
 * storage, or a fetch wrapper — only "where is the API" and how to
 * build a URL against it. See the module docstring convention used
 * throughout backend/ for why: add capability when something actually
 * needs it, not preemptively.
 */

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy frontend/.env.example to " +
        "frontend/.env.local and set it to the backend API's base URL.",
    );
  }
  return baseUrl.replace(/\/+$/, "");
}

/**
 * Builds a full URL against the backend API base URL.
 *
 * @param path - A path relative to the API base, e.g. "service-requests/"
 *   or "/rules/metadata/" (leading/trailing slashes are normalized).
 */
export function buildApiUrl(path: string): string {
  const normalizedPath = path.replace(/^\/+/, "");
  return `${getApiBaseUrl()}/${normalizedPath}`;
}
