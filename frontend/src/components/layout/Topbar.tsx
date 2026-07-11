export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
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
      {/* Shell placeholder only — not wired to auth, no menu, no data. */}
      <div
        aria-hidden="true"
        title="User menu placeholder — not implemented yet"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-500"
      >
        —
      </div>
    </header>
  );
}
