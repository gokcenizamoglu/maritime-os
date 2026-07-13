/**
 * Server-only read/write access to the BFF relay cookies (see
 * cookies.ts for names/options). This is the ONLY module in the
 * frontend that touches `next/headers` `cookies()` for auth purposes —
 * every other file (apiFetch, Server Actions, pages) goes through the
 * functions here, never through `cookies()` directly, so the relay
 * mechanism can be swapped later (e.g. for an opaque server-side BFF
 * session store — see docs/AUTHENTICATION_ARCHITECTURE.md's future
 * evolution section) by changing this one file, not every call site.
 *
 * READ vs WRITE SPLIT IS LOAD-BEARING, NOT STYLE: Next.js's `cookies()`
 * only allows `.set()`/`.delete()` inside a Server Action or Route
 * Handler — calling them during a Server Component's render throws.
 * The getters below are safe anywhere (Server Components, Server
 * Actions, Route Handlers); the setters/clearers are ONLY safe to call
 * from a Server Action or Route Handler — every exported setter/clearer
 * says so explicitly in its own docstring, not just here.
 */
import { cookies } from "next/headers";
import { CSRF_RELAY_COOKIE, relayCookieOptions, SESSION_RELAY_COOKIE } from "./cookies";

export async function getSessionRelay(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(SESSION_RELAY_COOKIE)?.value;
}

export async function getCsrfRelay(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(CSRF_RELAY_COOKIE)?.value;
}

export async function hasSessionRelay(): Promise<boolean> {
  return Boolean(await getSessionRelay());
}

/** Server Action / Route Handler only — see module docstring. */
export async function setSessionRelay(sessionValue: string): Promise<void> {
  const store = await cookies();
  store.set(SESSION_RELAY_COOKIE, sessionValue, relayCookieOptions());
}

/** Server Action / Route Handler only — see module docstring. */
export async function setCsrfRelay(csrfToken: string): Promise<void> {
  const store = await cookies();
  store.set(CSRF_RELAY_COOKIE, csrfToken, relayCookieOptions());
}

/**
 * Server Action / Route Handler only — see module docstring. Used both
 * by an intentional logout and by callers that discover the relay is
 * stale — see
 * lib/api/client.ts's `kind: "unauthenticated"` / `"forbidden"` results.
 */
export async function clearAuthRelay(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_RELAY_COOKIE);
  store.delete(CSRF_RELAY_COOKIE);
}
