/**
 * Encapsulates the exact Django BFF login/logout HTTP sequence (see
 * docs/AUTHENTICATION_ARCHITECTURE.md) — every fetch to Django's
 * /api/auth/* endpoints happens here, nowhere else, so the multi-step
 * CSRF-bootstrap-then-login dance exists in exactly one place.
 *
 * Distinct from the domain `apiFetch` in lib/api/client.ts: apiFetch
 * assumes a relay cookie ALREADY exists and forwards it; the functions
 * here are what OBTAIN that relay in the first place, which requires
 * reading `Set-Cookie` response headers directly — something no other
 * caller in this codebase needs to do.
 *
 * This file never touches `next/headers` — it returns plain values
 * (session id, CSRF token, user) for the calling Server Action to hand
 * to lib/auth/session.ts. Keeping HTTP concerns and Next's cookie jar
 * in separate modules means this file has no dependency on running
 * inside a Next.js request context.
 *
 * VERIFIED, NOT ASSUMED: Node's `fetch()` (via undici) exposes raw
 * Set-Cookie values through `Response.headers.getSetCookie()` — unlike
 * a browser's `fetch()`, which hides Set-Cookie from JS entirely. This
 * was confirmed against a real running Django instance before writing
 * the extraction logic below, not assumed from browser-fetch behavior.
 */
import { buildApiUrl } from "@/lib/api/config";
import type { AuthenticatedUser } from "@/types/auth";

/** Django's own cookie/header names — this file is the only place allowed to know them, since it's the only code that speaks to Django directly rather than through the relay. */
export const DJANGO_SESSION_COOKIE_NAME = "sessionid";
export const DJANGO_CSRF_HEADER_NAME = "X-CSRFToken";

export type LoginOutcome =
  | { ok: true; sessionId: string; csrfToken: string; user: AuthenticatedUser }
  | { ok: false; reason: "invalid_credentials"; message: string }
  | { ok: false; reason: "network_error"; message: string }
  | { ok: false; reason: "unexpected_response"; message: string };

interface CsrfBootstrap {
  sessionId: string;
  csrfToken: string;
}

/**
 * Extracts just `name=value` from a raw Set-Cookie header string,
 * discarding attributes (Path, HttpOnly, Expires, ...) — those describe
 * how a BROWSER should store Django's cookie, which is irrelevant here:
 * Django's cookie is never given to the browser, only the credential
 * VALUE is relayed, under Next's own cookie name and attributes.
 */
function extractCookieValue(setCookieHeader: string, cookieName: string): string | null {
  const match = setCookieHeader.match(new RegExp(`^${cookieName}=([^;]+)`));
  return match ? match[1] : null;
}

function findDjangoSessionId(setCookieValues: string[]): string | null {
  for (const value of setCookieValues) {
    const sessionId = extractCookieValue(value, DJANGO_SESSION_COOKIE_NAME);
    if (sessionId) return sessionId;
  }
  return null;
}

/**
 * GET /api/auth/csrf/ against Django directly. Returns the masked CSRF
 * token AND the session id Django assigned to carry that token's
 * secret — needed even before login, because `CSRF_USE_SESSIONS` (see
 * backend/config/settings/base.py) ties the CSRF secret to a session from the very
 * first request, before any user is authenticated.
 */
async function fetchCsrfBootstrap(existingSessionId?: string): Promise<CsrfBootstrap | null> {
  const response = await fetch(buildApiUrl("auth/csrf/"), {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(existingSessionId ? { Cookie: `${DJANGO_SESSION_COOKIE_NAME}=${existingSessionId}` } : {}),
    },
    cache: "no-store",
  });
  if (!response.ok) return null;

  const rotatedSessionId = findDjangoSessionId(response.headers.getSetCookie());
  const body = (await response.json()) as { csrfToken: string };

  // No Set-Cookie means Django reused the session id we already sent
  // (still valid) rather than issuing a new one.
  return { sessionId: rotatedSessionId ?? existingSessionId ?? "", csrfToken: body.csrfToken };
}

/**
 * The full bootstrap-then-login sequence:
 *   1. GET /api/auth/csrf/ (pre-auth) -> pre-auth session id + token
 *   2. POST /api/auth/login/ with that session + token
 *   3. Django's `login()` ROTATES the session key (session-fixation
 *      defense, Django's own built-in behavior — see
 *      backend/users/views.py) -> capture the NEW session id
 *   4. The rotated session also invalidates the pre-login CSRF secret,
 *      so a second GET /api/auth/csrf/ (now authenticated) obtains a
 *      fresh token for subsequent requests.
 */
export async function performLogin(username: string, password: string): Promise<LoginOutcome> {
  let bootstrap: CsrfBootstrap | null;
  try {
    bootstrap = await fetchCsrfBootstrap();
  } catch (err) {
    return { ok: false, reason: "network_error", message: describeError(err) };
  }
  if (!bootstrap) {
    return { ok: false, reason: "network_error", message: "Could not reach the backend to start a login session." };
  }

  let loginResponse: Response;
  try {
    loginResponse = await fetch(buildApiUrl("auth/login/"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Cookie: `${DJANGO_SESSION_COOKIE_NAME}=${bootstrap.sessionId}`,
        [DJANGO_CSRF_HEADER_NAME]: bootstrap.csrfToken,
      },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch (err) {
    return { ok: false, reason: "network_error", message: describeError(err) };
  }

  if (loginResponse.status === 400) {
    return { ok: false, reason: "invalid_credentials", message: "Invalid username or password." };
  }
  if (!loginResponse.ok) {
    return { ok: false, reason: "unexpected_response", message: `Login failed with status ${loginResponse.status}.` };
  }

  const rotatedSessionId = findDjangoSessionId(loginResponse.headers.getSetCookie());
  if (!rotatedSessionId) {
    return { ok: false, reason: "unexpected_response", message: "Login succeeded but no session was issued." };
  }

  const user = (await loginResponse.json()) as AuthenticatedUser;

  let freshCsrf: CsrfBootstrap | null;
  try {
    freshCsrf = await fetchCsrfBootstrap(rotatedSessionId);
  } catch (err) {
    return { ok: false, reason: "network_error", message: describeError(err) };
  }
  if (!freshCsrf) {
    return { ok: false, reason: "unexpected_response", message: "Logged in but could not obtain a post-login CSRF token." };
  }

  return { ok: true, sessionId: rotatedSessionId, csrfToken: freshCsrf.csrfToken, user };
}

/**
 * Calls Django's real logout endpoint using the currently relayed
 * session + CSRF token — this is what actually invalidates the backend
 * session (backend/users/views.py::LogoutView calls django.contrib
 * .auth.logout()). Returns whether the remote call is CONFIRMED to have
 * succeeded; the calling Server Action clears the LOCAL relay cookies
 * regardless of this result — see that action's own docstring for why
 * (an unreachable backend must not leave the browser stuck "logged in"
 * locally, even though the remote session may outlive its own expiry
 * in that specific failure case).
 */
export async function performLogout(sessionId: string, csrfToken: string): Promise<{ remoteInvalidated: boolean }> {
  try {
    const response = await fetch(buildApiUrl("auth/logout/"), {
      method: "POST",
      headers: {
        Cookie: `${DJANGO_SESSION_COOKIE_NAME}=${sessionId}`,
        [DJANGO_CSRF_HEADER_NAME]: csrfToken,
      },
      cache: "no-store",
    });
    return { remoteInvalidated: response.status === 204 };
  } catch {
    return { remoteInvalidated: false };
  }
}

function describeError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
