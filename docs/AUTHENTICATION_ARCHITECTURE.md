# MaritimeOS — Authentication Architecture

Status: **Implemented and verified** (first internal-staff authentication
slice). This document describes what was actually built — every claim
below was verified against a running backend and/or a real browser
session while building it, not assumed. Where a design decision
deliberately deviates from an earlier proposal, that's called out
explicitly with the reason.

---

## 1. Architecture

```
Browser
  │  same-origin, HttpOnly relay cookies only
  ▼
Next.js (BFF)
  │  server-to-server, real Django Cookie + X-CSRFToken headers
  ▼
Django + DRF (SessionAuthentication)
```

- **Django remains the sole source of truth** for users, tenants,
  sessions, and permissions. Nothing in the frontend re-implements or
  second-guesses this — every real authorization decision is a Django
  API response, verified per request.
- **The browser talks only to Next.js.** It never sends a request to
  Django directly, and never holds a cookie Django would accept.
- **Next.js talks to Django server-to-server**, attaching the session
  and CSRF credentials itself on every request. This runs in Node.js,
  not the browser, so it is not subject to CORS — confirmed empirically
  in an earlier sprint and re-confirmed here: no CORS package or
  configuration exists anywhere in this codebase.
- **JWT was not used.** Auth.js was not used. CORS was not configured.
  BasicAuthentication was removed. See §9 for why.

## 2. Backend endpoints

All four live in the existing `users` app (`users/views.py`,
`users/serializers.py`) — no new Django app was created.

| Endpoint | Method | Auth required | Purpose |
|---|---|---|---|
| `/api/auth/csrf/` | GET | None | Establishes/reuses a session, returns a masked CSRF token |
| `/api/auth/login/` | POST | CSRF token (explicit `csrf_protect`, see §4) | Authenticates, creates a real Django session |
| `/api/auth/logout/` | POST | Session + CSRF | Invalidates the real Django session |
| `/api/auth/me/` | GET | Session | Returns the caller's own identity |

**`GET /api/auth/csrf/`** response:
```json
{ "csrfToken": "YS7gMBCmwOCjiYfjxUBbbhoFzQO1t3aihcbSU0ezYhh60ZTPITKpJOOIeCmdWm0n" }
```

**`POST /api/auth/login/`** request:
```json
{ "username": "ops-user", "password": "..." }
```
Success response (200) — identical shape to `/api/auth/me/`:
```json
{
  "id": 1, "username": "ops-user", "first_name": "", "last_name": "",
  "role": "ops", "tenant": { "id": 1, "name": "Liva Marine" }
}
```
Failure response (400) — deliberately **one generic message for every
rejection reason** (wrong username, wrong password, inactive user,
tenantless non-superuser):
```json
{ "detail": "Invalid credentials." }
```
Never reveals which of those reasons applies — a username-enumeration
side channel is closed by construction, not by convention.

**`POST /api/auth/logout/`** — 204 No Content on success.

**`GET /api/auth/me/`** — identical shape to login's success response.
Only these six fields, nothing else:
`id, username, first_name, last_name, role, tenant {id, name} | null`.

**Superusers**: `User.tenant` is nullable specifically for
platform-level superusers (see `users/models.py`). Login allows a
tenantless superuser through; `tenant` is returned as an explicit
`null`, not omitted. This does **not** grant them access to
tenant-scoped endpoints — `IsTenantMember` (`config/permissions.py`,
completely unmodified by this sprint) still requires a non-null tenant
for those, regardless of what login accepted.

## 3. CSRF bootstrap and rotation — the exact sequence

`backend/config/settings/base.py` sets `CSRF_USE_SESSIONS = True`: the CSRF secret
lives inside the Django session, not a separate `csrftoken` cookie.
This is the correct fit here — the browser never talks to Django, so
there is no browser-side reader of a separate CSRF cookie to begin
with. Requires `SessionMiddleware` before `CsrfViewMiddleware` in
`MIDDLEWARE`, which was already true.

The BFF's login flow (`frontend/src/lib/auth/backend-auth.ts::performLogin`):

1. `GET /api/auth/csrf/` (no session yet) → Django creates a pre-auth
   session, returns `{sessionId, csrfToken}` (session id extracted from
   the raw `Set-Cookie` response header — see §5).
2. `POST /api/auth/login/` with that pre-auth session's `Cookie` header
   and `X-CSRFToken`.
3. Django's `login()` call **rotates the session key** — Django's own
   built-in session-fixation defense, not something this code
   implements. The pre-auth session id is now dead.
4. The response's `Set-Cookie` carries the **new, authenticated**
   session id — captured the same way.
5. The CSRF secret rotated along with the session (both are tied
   together under `CSRF_USE_SESSIONS`), so the pre-login token is now
   invalid too. A **second** `GET /api/auth/csrf/`, this time using the
   authenticated session, obtains a fresh token for subsequent unsafe
   requests. (The login response body deliberately does not carry a
   fresh token — kept minimal, user-only — so this second call is used
   instead, exactly as anticipated when this was scoped.)

Verified with a real request sequence during development
(`enforce_csrf_checks=True`): a login POST with no CSRF token → 403; a
login using a token obtained from a session that later logged in and
tried to reuse the **pre-login** token → 403; the correct, freshly
bootstrapped token → 200 with a real session created.

### A real bug this caught

`rest_framework.views.APIView.as_view()` wraps every DRF view in
Django's `csrf_exempt` and delegates CSRF enforcement to
`SessionAuthentication.enforce_csrf()` — which only runs if
`authenticate()` already found an **existing logged-in user** on the
request. At login time there is no logged-in user yet — that's the
entire point of the endpoint — so DRF's own CSRF path never triggers,
and `LoginView` would otherwise have accepted an unauthenticated POST
with **no CSRF token at all**. Verified empirically while building
this (a login POST with no `X-CSRFToken` header succeeded, before the
fix). Fixed with an explicit
`@method_decorator(csrf_protect, name="dispatch")` on `LoginView`,
which restores Django's real, session-secret-based CSRF check
independent of DRF's authentication-gated shortcut.
`LogoutView`/`MeView` don't need this: both require `IsAuthenticated`,
which only passes when a real prior session exists, so
`SessionAuthentication.authenticate()` finds a genuine user and DRF's
own `enforce_csrf()` runs normally for those two.

## 4. Relay cookie implementation

`frontend/src/lib/auth/cookies.ts` — names and shared options.
`frontend/src/lib/auth/session.ts` — the **only** module that touches
`next/headers` `cookies()` for auth purposes.

| Cookie | Purpose | Flags |
|---|---|---|
| `mos_session` | Carries the Django session credential (see below) | `httpOnly`, `sameSite=lax`, `secure` in production, `path=/`, 14-day maxAge |
| `mos_csrf` | Carries the current Django CSRF token value | Same flags |

Deliberately **not** named `sessionid`/`csrftoken` (Django's own cookie
names) — a distinct name makes it obvious in devtools that this is a
Next.js-origin cookie, not a leaked Django one, and avoids any
collision if this app and Django ever share a top-level domain.

**In this first implementation, `mos_session`'s value IS the raw
Django session id.** This is an intentional, revisitable choice: the
read/write access is entirely centralized in `session.ts`, so replacing
this with an opaque server-side BFF session mapping later (§10) means
changing that one file, not every page or Server Action.

**Verified, not assumed:** Node's `fetch()` (via undici) exposes raw
`Set-Cookie` values through `Response.headers.getSetCookie()` — unlike
a browser's `fetch()`, which hides `Set-Cookie` from JS entirely. This
was confirmed against a real running Django instance before writing the
extraction logic in `backend-auth.ts`.

**Read vs. write split is load-bearing, not style.** Next.js only
allows `cookies().set()`/`.delete()` inside a Server Action or Route
Handler — calling them during a Server Component's render throws
(confirmed against Next's own docs before writing any code). The
getters in `session.ts` (`getSessionRelay`, `getCsrfRelay`,
`hasSessionRelay`) are safe anywhere; the setters/clearers
(`setSessionRelay`, `setCsrfRelay`, `clearAuthRelay`) are **only** safe
from a Server Action or Route Handler, and every one says so in its own
docstring.

**Never exposed to the browser or client code.** Confirmed with a real
browser session after logging in: `document.cookie` (the only
JS-readable cookie surface) returned an empty string — the `httpOnly`
relay cookies are genuinely invisible to client-side JavaScript, not
just conventionally treated as such. No credential string appears
anywhere in rendered HTML.

## 5. `apiFetch` — the auth-aware fetch layer

`frontend/src/lib/api/client.ts` now reads the relay cookies on every
call and forwards them as Django's real `Cookie: sessionid=...` header
(always) and `X-CSRFToken` header (for any method other than
GET/HEAD/OPTIONS). This required splitting `ApiResult`/`describeApiError`
into a new dependency-free module, `frontend/src/lib/api/result.ts` —
`client.ts` now depends on `next/headers` (via the session relay), which
Next.js refuses to bundle into a Client Component. `ApiErrorState`
(rendered from inside the Client-Component `ServiceRequestTabs`) needed
`ApiResult`/`describeApiError` without pulling in that server-only
dependency chain — confirmed by an actual Turbopack build failure
before this split existed, not a hypothetical.

`ApiResult` failure kinds, precisely distinguished (not collapsed into
one generic bucket):

| Kind | Meaning | Detection |
|---|---|---|
| `unauthenticated` | 401, or 403 with no relay cookie ever sent | No credential was ever presented |
| `forbidden` | 403 with a relay cookie present, valid JSON body | See caveat below |
| `csrf_failure` | 403 with a **non-JSON** body | Django's own CSRF rejection page (HTML), bypassing DRF's JSON exception handling entirely — a reliable, empirically confirmed signal, since every other 403 in this codebase returns valid JSON |
| `network_error` | Backend unreachable | fetch() itself threw |
| `parse_error` | 2xx status, unparseable body | Distinct from throwing uncaught inside `apiFetch` |
| `config_error` | `NEXT_PUBLIC_API_BASE_URL` unset | Unchanged from before this sprint |

**Caveat on `forbidden` vs. `unauthenticated`, stated honestly:** DRF's
default exception handling does not distinguish "your session is
invalid/expired" from "you're authenticated but not permitted here" at
the HTTP level in this project's current configuration — both surface
as 403 with a `{"detail": "..."}` body (verified empirically). Callers
should generally treat `forbidden` the same as `unauthenticated` (offer
re-login) until the backend grows a permission model that actually
needs the distinction.

## 6. `(app)/layout.tsx` — the real auth gate

`frontend/src/app/(app)/layout.tsx` wraps every internal-app route
(dashboard, operations, documents, automation) inside a Next.js **route
group**. It calls `GET /api/auth/me/` on every request and redirects to
`/login` if that fails, for any reason. This is the actual,
Django-verified gate — not a cookie-presence check.

### A second real bug this caught

Without `export const dynamic = "force-dynamic"` on this layout,
`next build` prerendered it **once**, at build time, with no real
session — baking in a permanent, cached "redirect to `/login`" response
served to every subsequent request, **including ones with a genuinely
valid session**. Confirmed empirically: after a real login, curling
`/dashboard` with the real session cookie still returned the identical
cached 307 (`x-nextjs-cache: HIT`, same ETag) as an anonymous request,
until this directive was added. `cookies()`'s own documentation claims
using it "will opt a route into dynamic rendering" automatically — that
auto-detection did not reliably propagate through this layout's async
call chain (`apiFetch` → `getSessionRelay` → `cookies()`). The same
lesson had already been learned once for `/operations` in an earlier
sprint; it needed relearning here rather than assuming it generalized.
**Lesson generalized for real this time:** always mark a route
`force-dynamic` explicitly when its rendering depends on `cookies()` or
live backend state, regardless of how many layers of function calls
separate it from the actual `cookies()`/`fetch()` call.

Does **not** clear a stale relay cookie itself — Next.js does not allow
cookie mutation during a layout's render. This is safe to leave as-is
because nothing in this app trusts the relay cookie's mere presence
anywhere (see §7) — a stale cookie left behind is simply inert until
overwritten by the next successful login or removed by logout.

## 7. `/login` and the redirect-loop that almost happened

`frontend/src/app/login/page.tsx` checks authentication the exact same
way as `(app)/layout.tsx` — a real `GET /api/auth/me/` call, **not**
relay-cookie presence. This was a deliberate correction during
implementation: an earlier draft checked cookie presence only, which
creates a genuine infinite-redirect loop with a stale cookie:

1. Stale cookie present → `/login`'s presence-based check sends the
   visitor to `/dashboard`.
2. `(app)/layout.tsx`'s real check finds the session invalid → redirects
   back to `/login`.
3. `/login`'s presence check sees the same (still present, never
   cleared — see §6) cookie → sends them to `/dashboard` again →
   forever.

Fixed by making **both** checks equally authoritative (both call
Django), so they always agree and the loop cannot occur.

**`proxy.ts` (§8) deliberately only redirects INTO `/login`, never away
from it**, for the same reason — a presence-based "redirect away from
login" at the Proxy layer would reintroduce this exact loop, one layer
higher, and Proxy cannot mutate cookies to break it either.

## 8. `proxy.ts` — UX-only fast path

Next.js 16 renamed the `middleware.ts` file convention to `proxy.ts`
(confirmed against this project's actual installed Next.js version,
16.2.10, by reading the bundled framework documentation before writing
this file — not assumed from training data, which predates this
rename). `frontend/src/proxy.ts` checks only whether the `mos_session`
cookie is **present** on requests to `/dashboard`, `/operations`,
`/documents`, `/automation` — if absent, redirects to
`/login?next=<path>`. That's the entire check.

**Never treated as authorization.** A present-but-stale cookie is not
caught here — that's `(app)/layout.tsx`'s job (§6), which calls the
real API on every request regardless of what Proxy decided. Proxy
exists purely to avoid rendering a page at all when there's obviously
no credential to try.

## 9. Why not JWT / Auth.js / browser-direct Django

- **JWT**: doesn't solve the Server-Component-fetch problem any
  differently — a JWT still has to live in an httpOnly cookie relayed
  the same way (or be manually attached from somewhere Server
  Components can reach, which is the same relay problem again), and
  adds real revocation weakness (a leaked/stolen JWT stays valid until
  expiry without a server-side denylist, which then reintroduces the
  statefulness JWT was supposed to avoid) plus refresh-flow complexity,
  for a single first-party internal tool with no third-party API
  consumers. Rejected.
- **Auth.js**: no concrete need identified — Django already owns
  authentication, sessions, and the user model; adding a
  frontend-side auth framework would duplicate that, not simplify it.
  Rejected.
- **Browser-direct Django (Approach A from the earlier proposal)**:
  Server Components have no way to obtain a cookie scoped to Django's
  origin — cookies are strictly scoped to the origin that set them, and
  a Server Component isn't the browser. Forces either abandoning
  Server-Component-driven data fetching (a large regression given the
  existing `/operations` implementation) or making the session cookie
  readable by client JS (an XSS-exposure regression). Also requires
  real CORS configuration and a publicly browser-reachable Django API —
  both explicitly avoided here. Rejected.

## 10. BasicAuthentication removal

`backend/config/settings/base.py` sets `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`
explicitly to `["rest_framework.authentication.SessionAuthentication"]`
— previously implicit (DRF's own default is
`[SessionAuthentication, BasicAuthentication]`). BasicAuthentication
accepted a username/password on **every single request** with no rate
limiting or lockout — redundant attack surface now that a real login
flow exists. Nothing in this codebase's tests or runtime depended on
it: the Django/DRF test client authenticates via `force_authenticate()`
/ `client.login()` / a real CSRF-bootstrapped login sequence, none of
which use HTTP Basic. Verified with a dedicated regression test
(`users/tests.py::SessionAuthenticationConfigurationTests::test_basic_authentication_credentials_are_no_longer_accepted`):
valid Basic credentials sent today are rejected exactly as if no
credentials were sent at all.

## 11. Local development

```bash
# backend/
python manage.py migrate
python manage.py runserver 8000

# frontend/
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api" > .env.local
npm run build && npm run start   # or npm run dev
```

No CORS configuration needed — Next's server-to-server calls to Django
are not browser requests. `secure` on the relay cookies is conditional
on `NODE_ENV === "production"`, so local HTTP works without the browser
silently refusing to store them (a `Secure` cookie is never sent over
plain HTTP).

## 12. Production hardening (deferred, not implemented here)

- `SESSION_COOKIE_SECURE = True`, and confirm the relay cookies'
  `secure` flag is actually `true` in the deployed environment
  (`NODE_ENV=production`).
- HTTPS enforcement (`SECURE_SSL_REDIRECT` or equivalent at the
  reverse proxy).
- `CSRF_TRUSTED_ORIGINS` — only if the final deployment topology
  actually needs it (e.g. a reverse proxy terminating TLS on a
  different host than Django sees internally). Undecided until that
  topology is chosen.
- Session expiry policy tuning (`SESSION_COOKIE_AGE`) — currently
  Django's default (2 weeks), mirrored for display purposes only in the
  relay cookie's `maxAge`.
- Rate limiting / account lockout on `/api/auth/login/` — none exists
  today; a brute-force attempt against a valid username is currently
  only slowed by request latency, nothing else.
- Audit logging of login/logout events — `ActivityLog` exists in this
  codebase for business-fact auditing but is not wired to auth events;
  worth deciding deliberately, not bolting on silently.
- Same-domain, path-based reverse proxy deployment (Next.js and Django
  behind one public origin) — would not change this architecture, only
  the deployment topology; Next's server would still need to relay the
  session explicitly to its own outgoing fetch regardless.

## 13. Future evolution path

- **Opaque server-side BFF session store**: replace `mos_session`'s
  current raw-Django-session-id value with an opaque token Next.js maps
  server-side to the real Django session (and whatever else a session
  needs to carry later) — `session.ts`'s read/write functions are the
  only code that would need to change; every page, Server Action, and
  `apiFetch` call site is already isolated from this detail.
- **Redis-backed mapping**: only if genuine scale or security
  requirements justify it (e.g. multiple Next.js instances needing
  shared session-relay state) — not needed for a single-instance
  deployment.
- **Separate mobile/third-party API auth**: explicitly out of scope
  here. If a client emerges that can't participate in the BFF cookie
  relay (a mobile app, a third-party integration), it needs its own
  auth mechanism (token-based is the natural fit) — this does not
  require changing anything internal staff currently use, per the
  original constraint that this implementation stay adaptable to that
  without redesigning it now.
- **Customer portal authentication**: remains a fully separate future
  decision, deliberately not designed here. The existing
  `UploadLink`/`public_upload_view` token-based pattern (already in
  this codebase, unrelated to this sprint) is real prior art for what a
  customer-facing, no-login access model already looks like in this
  system, worth reusing as a reference point when that decision is
  made.

## 14. Role enforcement — a pre-existing gap, unchanged by this sprint

`User.role` (Admin/Ops/Viewer) exists on the model and is now visible
in `/api/auth/me/`'s response, but **no permission class in this
codebase enforces it** — `IsTenantMember` only checks tenant
membership. This was true before this sprint and remains true after
it; surfacing the role in the API response makes the gap more visible
in the frontend, but does not close it. Any future frontend behavior
that varies by role must not be treated as a security boundary until a
real backend permission class enforces it — the same principle applied
throughout this document to relay-cookie presence.
