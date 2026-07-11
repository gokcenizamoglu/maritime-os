"use client";

import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Persistent desktop sidebar + compact topbar + content area. Sidebar is
 * always visible at md+ (desktop-first, per docs/DESIGN_SYSTEM.md §12);
 * below that it becomes an off-canvas panel toggled from the topbar —
 * plain React state, no external library, per the constraint not to
 * install one for this slice.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-full">
      <div className="hidden md:block md:w-60 md:shrink-0 md:border-r md:border-black/[.08]">
        <Sidebar />
      </div>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileNavOpen(false)}
          />
          <div className="relative z-10 h-full w-64 border-r border-black/[.08] bg-white shadow-lg">
            <Sidebar onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setMobileNavOpen((open) => !open)} />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
