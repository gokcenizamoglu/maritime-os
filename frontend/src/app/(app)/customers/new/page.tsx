import { CustomerForm } from "@/components/customers/CustomerForm";
import { createCustomer } from "@/lib/actions";

export const dynamic = "force-dynamic";

export default function NewCustomerPage() {
  return (
    <div className="mx-auto max-w-lg p-6">
      <div className="mb-6 border-b border-black/[.08] pb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">New Customer</h1>
        <p className="mt-1 text-sm text-zinc-600">Add a new customer company.</p>
      </div>
      <CustomerForm action={createCustomer} />
    </div>
  );
}
