import { logoutAction } from "@/lib/auth/actions";
import type { AuthenticatedUser } from "@/types/auth";

function displayName(user: AuthenticatedUser): string {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return fullName || user.username;
}

function initials(user: AuthenticatedUser): string {
  const name = displayName(user);
  const parts = name.trim().split(/\s+/);
  const letters = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [name.slice(0, 2)];
  return letters.join("").toUpperCase();
}

export function Topbar({ user, onMenuClick }: { user: AuthenticatedUser; onMenuClick: () => void }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-black/[.08] px-4">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Toggle navigation"
        className="rounded-md px-2 py-1 text-sm text-zinc-600 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 md:hidden"
      >
        Menu
      </button>
      <div className="hidden md:block" />

      {/* Real user, fetched server-side via GET /api/auth/me/ — see
          app/(app)/layout.tsx. Only fields the backend actually
          returns are shown here (id/username/first_name/last_name/
          role/tenant), nothing invented. */}
      <div className="flex items-center gap-3">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium text-zinc-900">{displayName(user)}</p>
          <p className="text-xs text-zinc-500">
            {user.tenant ? user.tenant.name : "No tenant"} · {user.role}
          </p>
        </div>
        <div
          aria-hidden="true"
          title={displayName(user)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-500"
        >
          {initials(user)}
        </div>
        <form action={logoutAction}>
          <button
            type="submit"
            className="rounded-md px-2 py-1 text-sm text-zinc-600 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            Sign out
          </button>
        </form>
      </div>
    </header>
  );
}
