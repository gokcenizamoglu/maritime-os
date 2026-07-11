/**
 * Generic status-pill primitive — tinted background + matching text,
 * per docs/DESIGN_SYSTEM.md §10 ("status is never conveyed by color
 * alone"). Domain-specific badges (ServiceRequest status, workflow step
 * status, ...) map their own enum to a `tone` + label and render this,
 * rather than each reimplementing the pill styling.
 */
const TONE_STYLE = {
  neutral: "bg-zinc-100 text-zinc-700",
  info: "bg-blue-50 text-blue-700",
  warning: "bg-amber-50 text-amber-700",
  success: "bg-green-50 text-green-700",
  danger: "bg-red-50 text-red-700",
} as const;

export type BadgeTone = keyof typeof TONE_STYLE;

export function Badge({ tone, children }: { tone: BadgeTone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${TONE_STYLE[tone]}`}
    >
      {children}
    </span>
  );
}
