import Link from "next/link";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "@/types/api";
import type { Customer } from "@/types/customer";
import type { AuthenticatedUser } from "@/types/auth";

export const dynamic = "force-dynamic";

async function getUser(): Promise<AuthenticatedUser | null> {
  const result = await apiFetch<AuthenticatedUser>("auth/me/");
  return result.ok ? result.data : null;
}

export default async function CustomersPage() {
  const [result, user] = await Promise.all([
    apiFetch<PaginatedResponse<Customer>>("customers/"),
    getUser(),
  ]);

  const canCreate = user?.capabilities.includes("customer.create") ?? false;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between border-b border-black/[.08] pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Customers</h1>
          <p className="mt-1 text-sm text-zinc-600">Manage your customer companies.</p>
        </div>
        {canCreate && (
          <Link
            href="/customers/new"
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            New Customer
          </Link>
        )}
      </div>

      {!result.ok && <ApiErrorState result={result} />}

      {result.ok && result.data.count === 0 && (
        <EmptyState
          title="No customers yet"
          description="Create your first customer to start managing operations."
        />
      )}

      {result.ok && result.data.count > 0 && (
        <div className="overflow-x-auto rounded-lg border border-black/[.08]">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-black/[.08] bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Email</th>
                <th className="px-3 py-2 font-medium">Phone</th>
                <th className="px-3 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {result.data.results.map((customer) => (
                <tr key={customer.id} className="border-b border-black/[.06] last:border-0 hover:bg-zinc-50">
                  <td className="px-3 py-2">
                    <Link
                      href={`/customers/${customer.id}/edit`}
                      className="font-medium text-zinc-900 hover:underline"
                    >
                      {customer.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-zinc-700">{customer.contact_email || "—"}</td>
                  <td className="px-3 py-2 text-zinc-700">{customer.contact_phone || "—"}</td>
                  <td className="px-3 py-2 text-zinc-500">
                    {new Date(customer.created_at).toLocaleDateString(undefined, {
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
