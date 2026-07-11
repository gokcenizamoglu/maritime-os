# MaritimeOS — Frontend Design System

Status: **Phase 1 decisions locked below are final for this slice.** Sections
marked *Deferred* or *Needs confirmation* are not yet decided — do not treat
them as implemented or as product commitments.

This document reflects an internal proposal reviewed and narrowed down to a
concrete, implementable Phase 1 scope. It supersedes the exploratory proposal
in favor of the specific values below wherever they conflict.

---

## 1. Product visual personality — DECIDED

Modern enterprise operations SaaS. Dense, calm, neutral. Built for internal
operations staff, coordinators, managers, and survey teams using the product
for long stretches of the workday — not a marketing site, not a consumer app.

Explicitly excluded: gradients, waves, anchors, compass roses, ship
silhouettes, ocean photography, decorative marine iconography, and any
"nautical" display typography. Brand personality comes from information
clarity and consistency, not decoration.

## 2. Color system — DECIDED (roles), Needs confirmation (exact brand hex)

| Token | Role | Status |
|---|---|---|
| `background` | Page canvas, near-white cool neutral | Decided |
| `surface` | Cards, tables, panels — white | Decided |
| `border` | Subtle dividers (default) / stronger emphasis (inputs, tables) | Decided |
| `primary` | Brand action color | **Needs confirmation** — proposed default: a restrained blue (`#2563EB` family). This is a placeholder, not a brand decision. |
| `secondary` | Neutral-toned action color — deliberately NOT a second saturated hue, to keep the palette restrained | Decided |
| `text` | Primary text, near-black neutral (not pure black) | Decided |
| `muted text` | Labels, helper text, timestamps | Decided |
| `success` | Completed / approved | Decided |
| `warning` | Blocked / needs attention | Decided |
| `danger` | Rejected / failed / destructive | Decided |
| `info` | Reuses `primary` at a lighter tint rather than a 5th hue | Decided |

**Hard rule:** status is never conveyed by color alone — every status indicator pairs color with a text label. Exact hex values must meet WCAG AA contrast once `primary` is confirmed.

## 3. Typography — DECIDED

- **Font family:** Geist Sans (UI text) / Geist Mono (reference codes, timestamps, tabular data) — already installed via `next/font/google`, no new dependency.
- **Body text:** **15px** (approved value for this slice — not the 14px explored earlier, and not the 16px web default). Dense enough for an operations tool, still comfortable for all-day reading.
- **Dense table text:** **13px**, tabular figures for numeric columns.
- **Headings:** H1 20–24px semibold (page title only) / H2 16–18px semibold (section) / H3 14–15px semibold (card/subsection).
- **Labels / helper text:** 12–13px, muted color, medium weight for labels.
- Never below 12px anywhere.

## 4. Spacing scale — DECIDED

Tailwind's **default 4px-based spacing scale** — no custom scale invented.
Documented usage convention, not new tokens:

| Context | Spacing |
|---|---|
| Form field vertical rhythm | `gap-4` |
| Card/panel padding | `p-4` (compact) / `p-6` (standard) |
| Table cell padding | `px-3 py-2` |
| Page content padding | `px-6 py-6` |

## 5. Border radius — DECIDED

- Inputs, buttons, badges, table hover: `rounded-md` (6px)
- Cards, modals, drawers, panels: `rounded-lg` (8px)
- Avatars, status dots, count pills only: `rounded-full`
- Never `rounded-2xl`/`rounded-3xl` — reads as consumer/marketing.

## 6. Shadows — DECIDED

Flat, bordered surfaces by default (cards, tables, sidebar) — **no shadow**.
Shadows reserved for genuine elevation above the page: dropdowns/popovers
(`shadow-sm`), modals/drawers/toasts (`shadow-md`/`shadow-lg`). Never a large
soft "glow" shadow.

## 7. Icon strategy — Recommended, NOT installed

**Recommendation carried forward, not acted on:** Lucide (`lucide-react`) —
consistent geometric line icons, standard pairing with Tailwind. **Not
installed in this slice.** Until installed, the shell uses plain text labels
and CSS-only placeholders (see `FRONTEND_INFORMATION_ARCHITECTURE.md` §3).

## 8. Layout — DECIDED (skeleton), applies to Phase 1 shell

- Sidebar: persistent, left, desktop-first.
- Topbar: slim, non-marketing.
- Content: fluid full-width for lists/dashboards; `max-w-2xl`/`max-w-3xl` reserved for single-column forms only.
- Page header pattern: optional breadcrumb → title → optional description → primary action(s) right-aligned → divider.

## 9. Component standards — Recommended shape, not all built yet

Buttons / inputs / selects / textareas / cards / data tables / badges /
alerts / modals / drawers / tabs / empty states — standards as described in
the original proposal remain the target shape. **Only what Stage 3/4 of the
current implementation slice actually builds exists in code today** (see
`FRONTEND_INFORMATION_ARCHITECTURE.md` for what that is). Do not assume any
component listed here exists as a reusable primitive yet unless it was
actually implemented.

## 10. Status and priority language — DECIDED (mapping), backend-verified values

One unified semantic color scale for both status and priority (not two
separate systems). Current real values, verified against
`backend/service_requests/models.py::ServiceRequest.Status` (the only status
enum wired into the frontend in this slice):

| Backend value | Label | Color |
|---|---|---|
| `draft` | Draft | Neutral/gray |
| `collecting_documents` | Collecting Documents | Neutral/gray |
| `ready` | Ready | Info/blue |
| `in_progress` | In Progress | Info/blue |
| `waiting_external` | Waiting External | Warning/amber |
| `completed` | Completed | Success/green |

No `priority` field exists on `ServiceRequest` today — priority styling is a
future concept, not implemented.

## 11. Accessibility requirements — DECIDED

WCAG 2.1 AA contrast minimum. Status never color-only. Full keyboard
operability. Visible focus rings always (never suppressed without a
replacement). rem-based sizing. Minimum ~32px interactive hit target.

## 12. Responsive behavior — DECIDED

Desktop-first (1280px+ primary canvas), not desktop-only. Tablet: sidebar
collapses. Mobile: graceful degradation only (stacked forms, scrollable
tables) — no bespoke mobile IA in this slice.

## 13. Multi-tenant branding — Deferred

Not implemented in this slice. Light mode only, no tenant branding, no
per-tenant accent color. The color-role structure in §2 is designed to
support it later without restructuring, but no tenant customization exists
today.

## 14. Dark mode — Deferred

Explicitly out of scope for this slice. Light mode only.

## 15. Recommended UI foundation — Recommended, NOT installed

- **shadcn/ui** — recommended *pattern* (Radix + Tailwind, code-owned components) for when component implementation scales up. Not installed.
- **Radix primitives** — recommended for accessible Select/Dialog/Tabs/Popover/DropdownMenu behavior later. Not installed.
- **Lucide** — recommended icon library. Not installed.
- **TanStack Table** — recommended once a table needs sorting/filtering/virtualization at real volume. Not installed; not needed for the current Phase 1 list.

None of the above are installed as of this slice. `npm run build`/`npm run lint` must pass without them.
