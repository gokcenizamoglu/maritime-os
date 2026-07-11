"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isNavGroup, NAV_ITEMS, type NavEntry, type NavLeaf } from "@/config/navigation";
import { SITE_NAME } from "@/config/site";

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

const linkClasses = (active: boolean) =>
  `rounded-md px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ${
    active ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900"
  }`;

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="flex h-full flex-col gap-1 p-4">
      <div className="mb-4 px-2 text-sm font-semibold tracking-tight text-zinc-900">{SITE_NAME}</div>
      {NAV_ITEMS.map((entry) => (
        <NavEntryItem key={entry.label} entry={entry} pathname={pathname} onNavigate={onNavigate} />
      ))}
    </nav>
  );
}

function NavLink({ leaf, pathname, onNavigate }: { leaf: NavLeaf; pathname: string; onNavigate?: () => void }) {
  const active = isActive(pathname, leaf.href);
  return (
    <Link
      href={leaf.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={linkClasses(active)}
    >
      {leaf.label}
    </Link>
  );
}

function NavEntryItem({
  entry,
  pathname,
  onNavigate,
}: {
  entry: NavEntry;
  pathname: string;
  onNavigate?: () => void;
}) {
  if (!isNavGroup(entry)) {
    return <NavLink leaf={entry} pathname={pathname} onNavigate={onNavigate} />;
  }

  return (
    <div className="mt-2">
      <div className="px-2 text-xs font-medium uppercase tracking-wide text-zinc-400">{entry.label}</div>
      <div className="mt-1 flex flex-col gap-1">
        {entry.children.map((child) => (
          <NavLink key={child.href} leaf={child} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </div>
    </div>
  );
}
