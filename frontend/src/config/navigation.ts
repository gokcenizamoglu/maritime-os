/**
 * Phase-1 sidebar — the single source of truth for what's linked, per
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md §2. Every href here maps to a
 * route that either serves real backend data or a clearly-labeled
 * placeholder — never a dead link to an area with no backend support
 * (Customers, Vessels, Organizations, Administration, Workflow Templates
 * are deliberately absent; see that doc for why).
 */
export interface NavLeaf {
  label: string;
  href: string;
}

export interface NavGroup {
  label: string;
  children: NavLeaf[];
}

export type NavEntry = NavLeaf | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return "children" in entry;
}

export const NAV_ITEMS: NavEntry[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Operations", href: "/operations" },
  { label: "Document Center", href: "/documents" },
  {
    label: "Automation",
    children: [{ label: "Rules", href: "/automation/rules" }],
  },
];
