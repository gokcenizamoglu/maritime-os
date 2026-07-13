import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import { sanitizeReturnPath } from "@/lib/auth/redirect";
import { SITE_NAME } from "@/config/site";
import type { AuthenticatedUser } from "@/types/auth";
import { LoginForm } from "./LoginForm";

export const dynamic = "force-dynamic";

interface LoginPageProps {
  searchParams: Promise<{ next?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;

  // Deliberately a REAL Django-verified check (GET /api/auth/me/), not
  // a relay-cookie-presence check: this page is also where a STALE
  // cookie's redirect loop would otherwise happen. If this instead
  // trusted cookie presence, a stale cookie would bounce the user to
  // /dashboard, whose own layout would find the SAME stale cookie
  // invalid via its own /api/auth/me/ call and send them back here —
  // and if proxy.ts also redirected away from /login on cookie
  // presence, that would loop forever at the proxy layer. Both checks
  // (here and in (app)/layout.tsx) call Django and agree, so no loop
  // is possible; see proxy.ts's own docstring for why it deliberately
  // does NOT redirect away from /login for this exact reason.
  const result = await apiFetch<AuthenticatedUser>("auth/me/");
  if (result.ok) {
    redirect(sanitizeReturnPath(params.next));
  }

  return (
    <div className="flex min-h-full flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">Sign in to {SITE_NAME}</h1>
        <p className="mt-1 text-sm text-zinc-600">Internal staff access.</p>
        <LoginForm nextPath={params.next} />
      </div>
    </div>
  );
}
