import { VesselForm } from "@/components/vessels/VesselForm";
import { createVessel } from "@/lib/actions";
import { apiFetch } from "@/lib/api/client";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import type { PaginatedResponse } from "@/types/api";
import type { Customer } from "@/types/customer";

export const dynamic = "force-dynamic";

export default async function NewVesselPage() {
  const result = await apiFetch<PaginatedResponse<Customer>>("customers/?page_size=100");

  if (!result.ok) {
    return (
      <div className="p-6">
        <ApiErrorState result={result} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <div className="mb-6 border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">New Vessel</h1>
        <p className="mt-1 text-sm text-zinc-600">Add a new vessel to your fleet.</p>
      </div>
      <VesselForm customers={result.data.results} action={createVessel} />
    </div>
  );
}
