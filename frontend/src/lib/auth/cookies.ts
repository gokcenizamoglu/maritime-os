/**
 * Centralized cookie names/options for the Next.js BFF session relay —
 * see docs/AUTHENTICATION_ARCHITECTURE.md. Single source of truth so no
 * page or Server Action ever hardcodes a cookie name or option set.
 *
 * Deliberately NOT named `sessionid`/`csrftoken` (Django's own cookie
 * names): a distinct, application-specific name makes it obvious in
 * devtools that this is a Next.js-origin cookie, not a leaked or
 * forwarded Django cookie, and avoids any collision if this app and
 * Django ever end up sharing a top-level domain.
 *
 * SERVER-ONLY BY FRAMEWORK ENFORCEMENT: every consumer of these names
 * uses `next/headers` `cookies()`, which Next.js itself refuses to run
 * outside a Server Component / Server Action / Route Handler — calling
 * it from a Client Component throws at the framework level. That
 * removes the need for a separate `server-only` package to enforce the
 * same boundary; nothing here is reachable from client code by
 * construction, not by convention.
 */

/** Carries the credential Next.js's server attaches as Django's Cookie header. In this first implementation, its value IS the Django session id — see backend-auth.ts's module docstring for why that's an intentional, revisitable choice, not a permanent commitment. */
export const SESSION_RELAY_COOKIE = "mos_session";

/** Carries the current Django-issued CSRF token value, relayed as the `X-CSRFToken` header on unsafe requests. Not a forwarded Django cookie — see config/settings/base.py's `CSRF_USE_SESSIONS = True`, which means Django itself never issues a separate CSRF cookie to relay in the first place. */
export const CSRF_RELAY_COOKIE = "mos_csrf";

/**
 * Mirrors Django's own default `SESSION_COOKIE_AGE` (2 weeks, in
 * seconds) purely so the two don't visibly disagree in a browser's
 * cookie inspector. This is a display-consistency choice, not an
 * enforcement mechanism — Django's session expiry is the one that
 * actually matters; if this cookie outlives the Django session, the
 * relay is simply stale and every request using it correctly falls
 * into the "unauthenticated" path (see lib/api/client.ts).
 */
const RELAY_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 14;

export interface RelayCookieOptions {
  httpOnly: true;
  sameSite: "lax";
  secure: boolean;
  path: string;
  maxAge: number;
}

/**
 * `secure` is conditional on `NODE_ENV`, not hardcoded true, because
 * local development runs over plain HTTP — a `Secure` cookie is never
 * sent by the browser over HTTP at all, which would silently break
 * every local login. See docs/AUTHENTICATION_ARCHITECTURE.md's
 * production-hardening section for the explicit requirement that this
 * MUST be true wherever the app is actually deployed over HTTPS.
 */
export function relayCookieOptions(): RelayCookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: RELAY_COOKIE_MAX_AGE_SECONDS,
  };
}
