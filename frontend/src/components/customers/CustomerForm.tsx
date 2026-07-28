"use client";

import { useRouter } from "next/navigation";
import { useActionState } from "react";
import type { Customer } from "@/types/customer";
import type { ActionResult } from "@/lib/actions";

interface CustomerFormProps {
  customer?: Customer;
  action: (formData: FormData) => Promise<ActionResult>;
}

export function CustomerForm({ customer, action }: CustomerFormProps) {
  const router = useRouter();
  const [state, formAction, isPending] = useActionState(
    async (_prev: ActionResult | null, formData: FormData) => {
      const result = await action(formData);
      if (result.ok) {
        router.push("/customers");
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
        <label htmlFor="name" className="block text-sm font-medium text-zinc-700">
          Company Name <span className="text-red-500">*</span>
        </label>
        <input
          id="name"
          name="name"
          type="text"
          required
          defaultValue={customer?.name ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div>
        <label htmlFor="contact_email" className="block text-sm font-medium text-zinc-700">
          Contact Email
        </label>
        <input
          id="contact_email"
          name="contact_email"
          type="email"
          defaultValue={customer?.contact_email ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div>
        <label htmlFor="contact_phone" className="block text-sm font-medium text-zinc-700">
          Contact Phone
        </label>
        <input
          id="contact_phone"
          name="contact_phone"
          type="tel"
          defaultValue={customer?.contact_phone ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div>
        <label htmlFor="notes" className="block text-sm font-medium text-zinc-700">
          Notes
        </label>
        <textarea
          id="notes"
          name="notes"
          rows={3}
          defaultValue={customer?.notes ?? ""}
          className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>

      <div className="flex gap-3 pt-2">
        <button
          type="submit"
          disabled={isPending}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
        >
          {isPending ? "Saving..." : customer ? "Update" : "Create"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/customers")}
          className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
