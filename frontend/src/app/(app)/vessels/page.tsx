import Link from "next/link";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "@/types/api";
import type { Vessel } from "@/types/vessel";
import type { AuthenticatedUser } from "@/types/auth";

export const dynamic = "force-dynamic";

async function getUser(): Promise<AuthenticatedUser | null> {
  const result = await apiFetch<AuthenticatedUser>("auth/me/");
  return result.ok ? result.data : null;
}

export default async function VesselsPage() {
  const [result, user] = await Promise.all([
    apiFetch<PaginatedResponse<Vessel>>("vessels/"),
    getUser(),
  ]);

  const canCreate = user?.capabilities.includes("vessel.create") ?? false;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between border-b border-black/[.08] pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Vessels</h1>
          <p className="mt-1 text-sm text-zinc-600">Manage your fleet.</p>
        </div>
        {canCreate && (
          <Link
            href="/vessels/new"
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            New Vessel
          </Link>
        )}
      </div>

      {!result.ok && <ApiErrorState result={result} />}

      {result.ok && result.data.count === 0 && (
        <EmptyState
          title="No vessels yet"
          description="Create your first vessel to start managing operations."
        />
      )}

      {result.ok && result.data.count > 0 && (
        <div className="overflow-x-auto rounded-lg border border-black/[.08]">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-black/[.08] bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">IMO</th>
                <th className="px-3 py-2 font-medium">Customer</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Flag</th>
                <th className="px-3 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {result.data.results.map((vessel) => (
                <tr key={vessel.id} className="border-b border-black/[.06] last:border-0 hover:bg-zinc-50">
                  <td className="px-3 py-2">
                    <Link
                      href={`/vessels/${vessel.id}/edit`}
                      className="font-medium text-zinc-900 hover:underline"
                    >
                      {vessel.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono text-zinc-700">{vessel.imo_number}</td>
                  <td className="px-3 py-2 text-zinc-700">{vessel.customer_name}</td>
                  <td className="px-3 py-2 text-zinc-700">{vessel.vessel_type || "—"}</td>
                  <td className="px-3 py-2 text-zinc-700">{vessel.current_flag_name ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-500">
                    {new Date(vessel.created_at).toLocaleDateString(undefined, {
                      year: "numeric", month: "short", day: "numeric",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
