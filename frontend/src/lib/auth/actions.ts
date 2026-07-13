"use server";

import { redirect } from "next/navigation";
import { performLogout } from "./backend-auth";
import { clearAuthRelay, getCsrfRelay, getSessionRelay } from "./session";

/**
 * Logout is two ordered steps:
 *   1. Tell Django to invalidate the REAL session — the only thing
 *      that actually matters security-wise (see
 *      backend/users/views.py::LogoutView, which calls
 *      django.contrib.auth.logout()).
 *   2. Clear the local relay cookies regardless of whether step 1
 *      succeeded, so the browser is never left "looking logged in"
 *      here even if Django was unreachable.
 *
 * If Django is unreachable, this does NOT claim the remote session was
 * invalidated — see docs/AUTHENTICATION_ARCHITECTURE.md's stale-session
 * section. The remote session may remain valid until its own natural
 * expiry in that specific failure case; nothing here pretends
 * otherwise.
 */
export async function logoutAction(): Promise<void> {
  const sessionId = await getSessionRelay();
  const csrfToken = await getCsrfRelay();

  if (sessionId && csrfToken) {
    await performLogout(sessionId, csrfToken);
  }

  await clearAuthRelay();
  redirect("/login");
}
