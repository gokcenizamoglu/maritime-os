"use client";

import { useActionState } from "react";
import { loginAction, type LoginFormState } from "./actions";

const initialLoginFormState: LoginFormState = { error: null };

/**
 * Client Component ONLY for pending/error UI state via React's built-in
 * `useActionState` (react-dom, already a dependency — no new package).
 * The actual credential submission happens server-side inside
 * `loginAction`; nothing here stores the username/password beyond the
 * form's own native, uncontrolled field state during submission.
 */
export function LoginForm({ nextPath }: { nextPath?: string }) {
  const [state, formAction, isPending] = useActionState(loginAction, initialLoginFormState);

  return (
    <form action={formAction} className="mt-6 flex flex-col gap-4">
      <input type="hidden" name="next" value={nextPath ?? ""} />

      <div className="flex flex-col gap-1">
        <label htmlFor="username" className="text-xs font-medium text-zinc-500">
          Username
        </label>
        <input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          required
          className="h-9 rounded-md border border-black/[.12] px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="password" className="text-xs font-medium text-zinc-500">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="h-9 rounded-md border border-black/[.12] px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
        />
      </div>

      {state.error && (
        <p role="alert" className="text-sm text-red-700">
          {state.error}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="h-9 rounded-md bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
      >
        {isPending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
