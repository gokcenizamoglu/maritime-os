import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { NewOperationForm } from "@/components/operations/NewOperationForm";
import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "@/types/api";
import type { Customer } from "@/types/customer";
import type { Vessel } from "@/types/vessel";
import type { ServiceOffering } from "@/types/catalog";

export const dynamic = "force-dynamic";

export default async function NewOperationPage() {
  const [customersResult, vesselsResult, offeringsResult] = await Promise.all([
    apiFetch<PaginatedResponse<Customer>>("customers/?page_size=25"),
    apiFetch<PaginatedResponse<Vessel>>("vessels/?page_size=25"),
    apiFetch<ServiceOffering[]>("service-offerings/available/"),
  ]);

  if (!customersResult.ok) {
    return <div className="p-6"><ApiErrorState result={customersResult} /></div>;
  }
  if (!vesselsResult.ok) {
    return <div className="p-6"><ApiErrorState result={vesselsResult} /></div>;
  }
  if (!offeringsResult.ok) {
    return <div className="p-6"><ApiErrorState result={offeringsResult} /></div>;
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <div className="mb-6 border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">New Operation</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Create a new service request by selecting a customer, vessel, and service offering.
        </p>
      </div>
      <NewOperationForm
        customers={customersResult.data.results}
        vessels={vesselsResult.data.results}
        offerings={offeringsResult.data}
      />
    </div>
  );
}
