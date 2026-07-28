"use client";

import { useRouter } from "next/navigation";
import { useActionState } from "react";
import type { Customer } from "@/types/customer";
import type { Vessel } from "@/types/vessel";
import type { ActionResult } from "@/lib/actions";

interface VesselFormProps {
  vessel?: Vessel;
  customers: Customer[];
  action: (formData: FormData) => Promise<ActionResult>;
}

export function VesselForm({ vessel, customers, action }: VesselFormProps) {
  const router = useRouter();
  const [state, formAction, isPending] = useActionState(
    async (_prev: ActionResult | null, formData: FormData) => {
      const result = await action(formData);
      if (result.ok) {
        router.push("/vessels");
      }
      return result;
    },
    null,
  );

  return (
    <form action={formAction} className="space-y-4">
      {state && !state.ok && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {state.error}
        </div>
      )}

      <div>
        <label htmlFor="customer" className="block text-sm font-medium text-zinc-700">
          Customer <span className="text-red-500">*</span>
        </label>
        <select
          id="customer"
          name="customer"
          required
          defaultValue={vessel?.customer ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        >
          <option value="">Select a customer...</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="name" className="block text-sm font-medium text-zinc-700">
          Vessel Name <span className="text-red-500">*</span>
        </label>
        <input
          id="name"
          name="name"
          type="text"
          required
          defaultValue={vessel?.name ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div>
        <label htmlFor="imo_number" className="block text-sm font-medium text-zinc-700">
          IMO Number <span className="text-red-500">*</span>
        </label>
        <input
          id="imo_number"
          name="imo_number"
          type="text"
          required
          defaultValue={vessel?.imo_number ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div>
        <label htmlFor="vessel_type" className="block text-sm font-medium text-zinc-700">
          Vessel Type
        </label>
        <input
          id="vessel_type"
          name="vessel_type"
          type="text"
          defaultValue={vessel?.vessel_type ?? ""}
          placeholder="e.g. Bulk Carrier, Container Ship"
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div className="flex gap-3 pt-2">
        <button
          type="submit"
          disabled={isPending}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
        >
          {isPending ? "Saving..." : vessel ? "Update" : "Create"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/vessels")}
          className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
