import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_RELAY_COOKIE } from "@/lib/auth/cookies";

/**
 * `proxy.ts` — Next.js 16's file convention, replacing the deprecated
 * `middleware.ts` (confirmed against this project's actual installed
 * Next.js version, 16.2.10, before writing this file — see
 * node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions
 * /proxy.md: "The `middleware` file convention is deprecated and has
 * been renamed to `proxy`.").
 *
 * UX-ONLY FAST PATH, NEVER AUTHORIZATION: this only checks whether the
 * relay cookie is PRESENT, never whether the session it names is still
 * valid — Proxy has no way to ask Django that (Proxy runs before any
 * route renders and shouldn't fetch the backend on every request for a
 * cheap check like this). A present-but-stale cookie is NOT caught
 * here; it's caught by app/(app)/layout.tsx, which calls the real
 * GET /api/auth/me/ on every request to an internal-app route and
 * redirects to /login if it fails, regardless of what Proxy decided.
 * Django remains authoritative on every real API request no matter
 * what Proxy does or gets wrong.
 *
 * DELIBERATELY ONE-DIRECTIONAL — redirects INTO /login, never AWAY from
 * it: the original design considered also redirecting an
 * already-has-a-cookie visitor away from /login as a UX nicety, but
 * that creates a real infinite-redirect loop with a STALE cookie:
 *   1. Stale cookie present -> Proxy sends /login visitor to /dashboard
 *   2. (app)/layout.tsx's real check finds the session invalid ->
 *      redirects back to /login
 *   3. Proxy sees the same (still present, still stale, never cleared
 *      here — Proxy cannot mutate cookies either) cookie -> sends them
 *      to /dashboard again -> forever.
 * /login/page.tsx's own server-side check (a real GET /api/auth/me/,
 * not a cookie-presence check) already redirects an already-authenticated
 * visitor away correctly, without this failure mode, because it agrees
 * with (app)/layout.tsx's check instead of contradicting it. See that
 * page for the corresponding half of this logic.
 */
const PROTECTED_PREFIXES = ["/dashboard", "/operations", "/documents", "/automation"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (!isProtected) {
    return NextResponse.next();
  }

  const hasRelay = request.cookies.has(SESSION_RELAY_COOKIE);
  if (hasRelay) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Excludes static assets and framework internals, per proxy.md's own
  // guidance — without this, Proxy runs on every request including
  // _next/static/_next/image/public assets, which would be wasted work
  // for paths that are never protected routes anyway.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
