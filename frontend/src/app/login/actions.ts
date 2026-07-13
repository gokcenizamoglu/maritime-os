"use server";

import { redirect } from "next/navigation";
import { performLogin } from "@/lib/auth/backend-auth";
import { sanitizeReturnPath } from "@/lib/auth/redirect";
import { setCsrfRelay, setSessionRelay } from "@/lib/auth/session";

/**
 * `interface` is fine to export from a "use server" file (erased at
 * compile time, not a runtime value) — but `initialLoginFormState`
 * previously exported here as a plain object was NOT, and Next.js
 * enforces this at runtime, not build time: "use server" files may
 * only export async functions. Confirmed by an actual browser-driven
 * login attempt failing with `Error: A "use server" file can only
 * export async functions, found object.` — `npm run build` did not
 * catch this. The constant now lives in LoginForm.tsx, the only place
 * that used it.
 */
export interface LoginFormState {
  error: string | null;
}

/**
 * `useActionState`-compatible Server Action — see app/login/LoginForm.tsx.
 * Never returns the specific reason a login failed beyond "credentials"
 * vs. "couldn't reach the server": mirrors
 * backend/users/views.py::LoginView's own "one generic response for
 * every rejection reason" principle, so this UI never reveals more than
 * the backend already refuses to.
 */
export async function loginAction(_prevState: LoginFormState, formData: FormData): Promise<LoginFormState> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const nextPath = sanitizeReturnPath(String(formData.get("next") ?? ""));

  if (!username || !password) {
    return { error: "Enter your username and password." };
  }

  const outcome = await performLogin(username, password);

  if (!outcome.ok) {
    if (outcome.reason === "invalid_credentials") {
      return { error: "Invalid username or password." };
    }
    // Network/unexpected-response failures are told apart from bad
    // credentials — an honest "couldn't reach the server" message
    // doesn't leak anything credential-related, and pretending a
    // backend outage is a typo'd password would be actively misleading.
    return { error: "Could not sign in right now. Please try again in a moment." };
  }

  await setSessionRelay(outcome.sessionId);
  await setCsrfRelay(outcome.csrfToken);

  redirect(nextPath);
}
