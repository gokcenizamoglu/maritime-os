"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useActionState, type FormEvent } from "react";
import type { Customer } from "@/types/customer";
import type { Vessel } from "@/types/vessel";
import type { ServiceOffering } from "@/types/catalog";
import type { ActionResult } from "@/lib/actions";
import { createServiceRequest, searchCustomers, searchVessels } from "@/lib/actions";
import { SearchableSelect } from "@/components/operations/SearchableSelect";

interface NewOperationFormProps {
  customers: Customer[];
  vessels: Vessel[];
  offerings: ServiceOffering[];
}

export function NewOperationForm({ customers, vessels, offerings }: NewOperationFormProps) {
  const router = useRouter();
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [selectedVesselId, setSelectedVesselId] = useState<string>("");
  const [selectedOfferingId, setSelectedOfferingId] = useState<string>("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [customerQuery, setCustomerQuery] = useState<string>("");
  const [customerOptions, setCustomerOptions] = useState<Customer[]>(customers);
  const [customerSearchError, setCustomerSearchError] = useState<string | null>(null);
  const [customerSearchPending, setCustomerSearchPending] = useState(false);
  const [vesselQuery, setVesselQuery] = useState<string>("");
  const [vesselOptions, setVesselOptions] = useState<Vessel[]>([]);
  const [vesselSearchError, setVesselSearchError] = useState<string | null>(null);
  const [vesselSearchPending, setVesselSearchPending] = useState(false);
  const customerSearchRequest = useRef(0);
  const vesselSearchRequest = useRef(0);
  const submitLock = useRef(false);

  useEffect(() => {
    const requestId = ++customerSearchRequest.current;
    const query = customerQuery.trim();

    if (!query) {
      return;
    }

    const timer = window.setTimeout(() => {
      setCustomerSearchPending(true);
      void searchCustomers(query).then((result) => {
        if (requestId !== customerSearchRequest.current) return;
        if (result.ok) {
          setCustomerOptions(result.items);
          setCustomerSearchError(null);
        } else {
          setCustomerOptions([]);
          setCustomerSearchError(result.error);
        }
        setCustomerSearchPending(false);
      });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [customerQuery, customers]);

  useEffect(() => {
    const requestId = ++vesselSearchRequest.current;
    if (!selectedCustomerId) {
      return;
    }

    const timer = window.setTimeout(() => {
      setVesselSearchPending(true);
      void searchVessels(Number(selectedCustomerId), vesselQuery.trim()).then((result) => {
        if (requestId !== vesselSearchRequest.current) return;
        if (result.ok) {
          setVesselOptions(result.items);
          setVesselSearchError(null);
        } else {
          setVesselOptions([]);
          setVesselSearchError(result.error);
        }
        setVesselSearchPending(false);
      });
    }, vesselQuery.trim() ? 250 : 0);

    return () => window.clearTimeout(timer);
  }, [selectedCustomerId, vesselQuery]);

  const selectedOffering = offerings.find((o) => o.id === Number(selectedOfferingId));
  const activeTemplates = selectedOffering?.template_variants.filter(
    (t) => t.is_active && t.published_version_id !== null,
  ) ?? [];

  const effectiveTemplateId = selectedTemplateId
    || (activeTemplates.length === 1 ? String(activeTemplates[0].id) : "");

  const [state, formAction, isPending] = useActionState(
    async (_prev: ActionResult | null, formData: FormData) => {
      const result = await createServiceRequest(formData);
      if (result.ok) {
        router.push(`/operations/${result.id}`);
      } else {
        submitLock.current = false;
      }
      return result;
    },
    null,
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    if (submitLock.current) {
      event.preventDefault();
      return;
    }
    submitLock.current = true;
  };

  const canSubmit = Boolean(
    selectedCustomerId && selectedVesselId && selectedOfferingId && effectiveTemplateId && !isPending,
  );
  const fieldErrors = state && !state.ok ? state.fieldErrors : undefined;
  const fieldError = (field: string) => fieldErrors?.[field]?.join(", ");

  return (
    <form action={formAction} onSubmit={handleSubmit} className="space-y-6">
      {state && !state.ok && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {state.error}
        </div>
      )}

      {/* Step 1: Customer */}
      <div>
        <label htmlFor="customer" className="block text-sm font-medium text-zinc-700">
          Customer <span className="text-red-500">*</span>
        </label>
        <SearchableSelect
          id="customer"
          name="customer"
          value={selectedCustomerId}
          searchValue={customerQuery}
          options={customerOptions.map((customer) => ({ id: customer.id, label: customer.name }))}
          placeholder="Select a customer..."
          searchPlaceholder="Search customers..."
          emptyMessage="No customers found."
          isLoading={customerSearchPending}
          error={customerSearchError}
          invalid={Boolean(fieldError("customer"))}
          onSearchChange={(value) => {
            setCustomerQuery(value);
            if (!value.trim()) {
              setCustomerOptions(customers);
              setCustomerSearchError(null);
              setCustomerSearchPending(false);
            }
            if (selectedCustomerId) {
              setSelectedCustomerId("");
              setSelectedVesselId("");
              setVesselQuery("");
              setVesselOptions([]);
              setVesselSearchError(null);
              setVesselSearchPending(false);
            }
          }}
          onChange={(value) => {
            const selectedCustomer = customerOptions.find((customer) => customer.id === Number(value));
            setSelectedCustomerId(value);
            setSelectedVesselId("");
            setVesselQuery("");
            setVesselOptions(vessels.filter((vessel) => vessel.customer === Number(value)));
            setVesselSearchError(null);
            setVesselSearchPending(false);
            setCustomerQuery(selectedCustomer?.name ?? "");
          }}
        />
        {fieldError("customer") && <p className="mt-1 text-sm text-red-700" role="alert">{fieldError("customer")}</p>}
      </div>

      {/* Step 2: Vessel (filtered by customer) */}
      {selectedCustomerId && (
        <div>
          <label htmlFor="vessel" className="block text-sm font-medium text-zinc-700">
            Vessel <span className="text-red-500">*</span>
          </label>
          <SearchableSelect
            id="vessel"
            name="vessel"
            value={selectedVesselId}
            searchValue={vesselQuery}
            options={vesselOptions.map((vessel) => ({
              id: vessel.id,
              label: `${vessel.name} (IMO ${vessel.imo_number})`,
            }))}
            placeholder="Select a vessel..."
            searchPlaceholder="Search vessels by name or IMO..."
            emptyMessage="No vessels found for this customer."
            isLoading={vesselSearchPending}
            error={vesselSearchError}
            invalid={Boolean(fieldError("vessel"))}
            onSearchChange={(value) => {
              setVesselQuery(value);
              if (selectedVesselId) setSelectedVesselId("");
            }}
            onChange={(value) => {
              const selectedVessel = vesselOptions.find((vessel) => vessel.id === Number(value));
              setSelectedVesselId(value);
              setVesselQuery(
                selectedVessel?.imo_number ?? "",
              );
            }}
          />
          {fieldError("vessel") && <p className="mt-1 text-sm text-red-700" role="alert">{fieldError("vessel")}</p>}
        </div>
      )}

      {/* Step 3: Service Offering */}
      {selectedVesselId && (
        <div>
          <label htmlFor="service_offering" className="block text-sm font-medium text-zinc-700">
            Service Offering <span className="text-red-500">*</span>
          </label>
          {offerings.length === 0 ? (
            <p className="mt-1 text-sm text-zinc-500">
              No service offerings are currently available.
            </p>
          ) : (
            <select
              id="service_offering"
              name="service_offering"
              required
              value={selectedOfferingId}
              aria-invalid={Boolean(fieldError("service_offering"))}
              onChange={(e) => {
                setSelectedOfferingId(e.target.value);
                setSelectedTemplateId("");
              }}
              className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            >
              <option value="">Select a service offering...</option>
              {offerings.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.display_name} - {o.service_type_name}
                  {o.flag_name ? ` (${o.flag_name})` : " (No flag context)"}
                  {o.flag_relationship_label ? ` - ${o.flag_relationship_label}` : ""}
                </option>
              ))}
            </select>
          )}
          {fieldError("service_offering") && <p className="mt-1 text-sm text-red-700" role="alert">{fieldError("service_offering")}</p>}
          {selectedOffering && activeTemplates.length === 0 && (
            <p className="mt-1 text-sm text-amber-700">
              No published operation template is available for this offering.
            </p>
          )}
          {selectedOffering && selectedOffering.description && (
            <p className="mt-1 text-xs text-zinc-500">{selectedOffering.description}</p>
          )}
        </div>
      )}

      {/* Step 4: Operation Template (optional, auto-selected if only one) */}
      {selectedOfferingId && activeTemplates.length > 1 && (
        <div>
          <label htmlFor="operation_template" className="block text-sm font-medium text-zinc-700">
            Operation Template
          </label>
          <select
            id="operation_template"
            name="operation_template"
            value={selectedTemplateId || effectiveTemplateId}
            aria-invalid={Boolean(fieldError("operation_template"))}
            onChange={(e) => setSelectedTemplateId(e.target.value)}
            className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          >
            <option value="">Select an operation template...</option>
            {activeTemplates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.code}){t.is_default ? " — default" : ""}
              </option>
            ))}
          </select>
          {fieldError("operation_template") && <p className="mt-1 text-sm text-red-700" role="alert">{fieldError("operation_template")}</p>}
        </div>
      )}

      {/* Hidden fields for template when auto-selected */}
      {effectiveTemplateId && activeTemplates.length <= 1 && (
        <input type="hidden" name="operation_template" value={effectiveTemplateId} />
      )}

      {/* Summary */}
      {selectedOfferingId && (
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
          <h3 className="text-sm font-medium text-zinc-900">Summary</h3>
          <dl className="mt-2 space-y-1 text-sm text-zinc-600">
            <div className="flex gap-2">
              <dt className="font-medium text-zinc-700">Customer:</dt>
              <dd>{customerOptions.find((customer) => customer.id === Number(selectedCustomerId))?.name}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="font-medium text-zinc-700">Vessel:</dt>
              <dd>{vesselOptions.find((vessel) => vessel.id === Number(selectedVesselId))?.name}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="font-medium text-zinc-700">Offering:</dt>
              <dd>{selectedOffering?.display_name}</dd>
            </div>
            {effectiveTemplateId && (
              <div className="flex gap-2">
                <dt className="font-medium text-zinc-700">Template:</dt>
                <dd>
                  {activeTemplates.find((t) => t.id === Number(effectiveTemplateId))?.name ?? "Auto"}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:opacity-50"
        >
          {isPending ? "Creating..." : "Create Operation"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/operations")}
          className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
