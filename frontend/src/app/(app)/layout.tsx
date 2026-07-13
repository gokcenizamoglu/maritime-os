import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api/client";
import type { AuthenticatedUser } from "@/types/auth";

/**
 * CRITICAL, VERIFIED NECESSARY — NOT BOILERPLATE: without this,
 * `next build` prerenders this layout (and every static child page
 * under it) ONCE at build time, when no real session exists, bakes in
 * the resulting "redirect to /login" as a STATIC, CACHED response, and
 * serves that SAME cached redirect to every subsequent request forever
 * — including ones with a genuinely valid session. Confirmed
 * empirically: after a real login, curling /dashboard with the real
 * session cookie still returned the same cached 307 (`x-nextjs-cache:
 * HIT`, identical ETag) as an anonymous request, until this directive
 * was added. `cookies()`'s own docs claim using it "will opt a route
 * into dynamic rendering" automatically, but that auto-detection did
 * NOT reliably propagate through this layout's async call chain
 * (apiFetch -> getSessionRelay -> cookies()) — same lesson already
 * learned for app/(app)/operations/page.tsx's identical directive;
 * applied here explicitly rather than trusted implicitly, twice now.
 */
export const dynamic = "force-dynamic";

/**
 * The REAL, Django-verified auth gate for every internal-app route
 * (dashboard/operations/documents/automation) — a route group layout
 * runs for every page nested under it, so this is one place, not one
 * per page. Calls GET /api/auth/me/ (requires a valid session) and
 * redirects to /login if it fails for ANY reason (no relay, stale
 * relay, forbidden) — see lib/api/client.ts's ApiResult kinds.
 *
 * Does NOT clear the stale relay cookie itself: Next.js only allows
 * cookie mutation from a Server Action or Route Handler, not during a
 * layout's render (see lib/auth/session.ts's module docstring). This
 * is safe to leave as-is because nothing in this app trusts the relay
 * cookie's mere PRESENCE anywhere — /login's own check also calls
 * /api/auth/me/ rather than checking for the cookie, so a stale cookie
 * left behind here is simply inert until overwritten by the next
 * successful login or removed by an explicit logout.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const result = await apiFetch<AuthenticatedUser>("auth/me/");

  if (!result.ok) {
    redirect("/login");
  }

  return <AppShell user={result.data}>{children}</AppShell>;
}
