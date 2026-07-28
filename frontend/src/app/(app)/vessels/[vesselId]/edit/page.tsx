import { redirect } from "next/navigation";
import { VesselForm } from "@/components/vessels/VesselForm";
import { updateVessel } from "@/lib/actions";
import { apiFetch } from "@/lib/api/client";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import type { PaginatedResponse } from "@/types/api";
import type { Customer } from "@/types/customer";
import type { Vessel } from "@/types/vessel";

export const dynamic = "force-dynamic";

interface EditVesselPageProps {
  params: Promise<{ vesselId: string }>;
}

export default async function EditVesselPage({ params }: EditVesselPageProps) {
  const { vesselId } = await params;
  const id = Number(vesselId);
  if (Number.isNaN(id)) redirect("/vessels");

  const [vesselResult, customersResult] = await Promise.all([
    apiFetch<Vessel>(`vessels/${id}/`),
    apiFetch<PaginatedResponse<Customer>>("customers/?page_size=100"),
  ]);

  if (!vesselResult.ok) {
    return (
      <div className="p-6">
        <ApiErrorState result={vesselResult} />
      </div>
    );
  }

  if (!customersResult.ok) {
    return (
      <div className="p-6">
        <ApiErrorState result={customersResult} />
      </div>
    );
  }

  const vessel = vesselResult.data;
  const boundAction = updateVessel.bind(null, id);

  return (
    <div className="mx-auto max-w-lg p-6">
      <div className="mb-6 border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Edit Vessel</h1>
        <p className="mt-1 text-sm text-zinc-600">{vessel.name}</p>
      </div>
      <VesselForm
        vessel={vessel}
        customers={customersResult.data.results}
        action={boundAction}
      />
    </div>
  );
}
