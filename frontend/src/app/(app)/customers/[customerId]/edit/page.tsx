import { redirect } from "next/navigation";
import { CustomerForm } from "@/components/customers/CustomerForm";
import { updateCustomer } from "@/lib/actions";
import { apiFetch } from "@/lib/api/client";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import type { Customer } from "@/types/customer";

export const dynamic = "force-dynamic";

interface EditCustomerPageProps {
  params: Promise<{ customerId: string }>;
}

export default async function EditCustomerPage({ params }: EditCustomerPageProps) {
  const { customerId } = await params;
  const id = Number(customerId);
  if (Number.isNaN(id)) redirect("/customers");

  const result = await apiFetch<Customer>(`customers/${id}/`);

  if (!result.ok) {
    return (
      <div className="p-6">
        <ApiErrorState result={result} />
      </div>
    );
  }

  const customer = result.data;
  const boundAction = updateCustomer.bind(null, id);

  return (
    <div className="mx-auto max-w-lg p-6">
      <div className="mb-6 border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Edit Customer</h1>
        <p className="mt-1 text-sm text-zinc-600">{customer.name}</p>
      </div>
      <CustomerForm customer={customer} action={boundAction} />
    </div>
  );
}
