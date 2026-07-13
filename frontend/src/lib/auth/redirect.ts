const FALLBACK_PATH = "/dashboard";

/**
 * Validates a caller-supplied "return to" path to prevent open
 * redirects — a malicious `?next=` value must never be able to send an
 * authenticated user's browser to an attacker-controlled origin right
 * after a successful login.
 *
 * Accepts ONLY same-origin relative paths starting with exactly one
 * `/`. Rejects:
 *   - absolute URLs (`https://evil.com`)
 *   - protocol-relative URLs (`//evil.com` — browsers resolve this to
 *     `https://evil.com` using the current page's protocol)
 *   - the backslash variant of the same trick (`/\evil.com`, which some
 *     browsers normalize to `//evil.com`)
 *
 * Falls back to `/dashboard` for anything else, including a missing
 * value.
 */
export function sanitizeReturnPath(candidate: string | null | undefined): string {
  if (!candidate) return FALLBACK_PATH;
  if (!candidate.startsWith("/")) return FALLBACK_PATH;
  if (candidate.startsWith("//")) return FALLBACK_PATH;
  if (candidate.startsWith("/\\")) return FALLBACK_PATH;
  return candidate;
}
