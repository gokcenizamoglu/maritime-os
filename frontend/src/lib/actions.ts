"use server";

import { apiFetch } from "@/lib/api/client";
import type { ApiResult } from "@/lib/api/result";
import type { ApiFieldErrors } from "@/types/api";
import type { PaginatedResponse } from "@/types/api";
import type { Customer } from "@/types/customer";
import type { Vessel } from "@/types/vessel";
import { revalidatePath } from "next/cache";

const SEARCH_PAGE_SIZE = 25;

export type ActionResult =
  | { ok: true; id: number }
  | { ok: false; error: string; fieldErrors?: ApiFieldErrors };

export type SearchResult<T> =
  | { ok: true; items: T[]; count: number }
  | { ok: false; error: string };

export async function searchCustomers(query: string): Promise<SearchResult<Customer>> {
  const params = new URLSearchParams({ page_size: String(SEARCH_PAGE_SIZE) });
  if (query.trim()) params.set("search", query.trim());
  const result = await apiFetch<PaginatedResponse<Customer>>(`customers/?${params.toString()}`);
  if (!result.ok) return { ok: false, error: describeError(result) };
  return { ok: true, items: result.data.results, count: result.data.count };
}

export async function searchVessels(
  customerId: number,
  query: string,
): Promise<SearchResult<Vessel>> {
  const params = new URLSearchParams({
    customer: String(customerId),
    page_size: String(SEARCH_PAGE_SIZE),
  });
  if (query.trim()) params.set("search", query.trim());
  const result = await apiFetch<PaginatedResponse<Vessel>>(`vessels/?${params.toString()}`);
  if (!result.ok) return { ok: false, error: describeError(result) };
  return { ok: true, items: result.data.results, count: result.data.count };
}

export async function createCustomer(formData: FormData): Promise<ActionResult> {
  const body = {
    name: formData.get("name"),
    contact_email: formData.get("contact_email") || "",
    contact_phone: formData.get("contact_phone") || "",
    notes: formData.get("notes") || "",
  };

  const result = await apiFetch<{ id: number }>("customers/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!result.ok) {
    return actionFailure(result);
  }

  revalidatePath("/customers");
  return { ok: true, id: result.data.id };
}

export async function updateCustomer(id: number, formData: FormData): Promise<ActionResult> {
  const body = {
    name: formData.get("name"),
    contact_email: formData.get("contact_email") || "",
    contact_phone: formData.get("contact_phone") || "",
    notes: formData.get("notes") || "",
  };

  const result = await apiFetch<{ id: number }>(`customers/${id}/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!result.ok) {
    return actionFailure(result);
  }

  revalidatePath("/customers");
  return { ok: true, id: result.data.id };
}

export async function createVessel(formData: FormData): Promise<ActionResult> {
  const body = {
    customer: Number(formData.get("customer")),
    name: formData.get("name"),
    imo_number: formData.get("imo_number"),
    vessel_type: formData.get("vessel_type") || "",
  };

  const result = await apiFetch<{ id: number }>("vessels/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!result.ok) {
    return actionFailure(result);
  }

  revalidatePath("/vessels");
  return { ok: true, id: result.data.id };
}

export async function updateVessel(id: number, formData: FormData): Promise<ActionResult> {
  const body: Record<string, unknown> = {
    name: formData.get("name"),
    imo_number: formData.get("imo_number"),
    vessel_type: formData.get("vessel_type") || "",
  };

  const customerVal = formData.get("customer");
  if (customerVal) body.customer = Number(customerVal);

  const result = await apiFetch<{ id: number }>(`vessels/${id}/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!result.ok) {
    return actionFailure(result);
  }

  revalidatePath("/vessels");
  return { ok: true, id: result.data.id };
}

export interface CreateServiceRequestPayload {
  customer: number;
  vessel: number;
  service_offering: number;
  operation_template: number;
}

export async function createServiceRequest(formData: FormData): Promise<ActionResult> {
  const operationTemplate = Number(formData.get("operation_template"));
  if (!operationTemplate) {
    return { ok: false, error: "Select an operation template before creating the operation." };
  }

  const body: CreateServiceRequestPayload = {
    customer: Number(formData.get("customer")),
    vessel: Number(formData.get("vessel")),
    service_offering: Number(formData.get("service_offering")),
    operation_template: operationTemplate,
  };

  const result = await apiFetch<{ id: number }>("service-requests/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!result.ok) {
    return actionFailure(result);
  }

  revalidatePath("/operations");
  return { ok: true, id: result.data.id };
}

function actionFailure(result: Exclude<ApiResult<unknown>, { ok: true }>): ActionResult {
  const fieldErrors =
    result.kind === "http_error" && result.error && !("detail" in result.error)
      ? result.error
      : undefined;
  return { ok: false, error: describeError(result), fieldErrors };
}

function describeError(result: Exclude<ApiResult<unknown>, { ok: true }>): string {
  switch (result.kind) {
    case "http_error": {
      if (!result.error) return `Request failed (${result.status})`;
      if ("detail" in result.error && typeof result.error.detail === "string") return result.error.detail;
      const msgs = Object.entries(result.error)
        .map(([f, m]) => `${f}: ${(m as string[]).join(", ")}`)
        .join("; ");
      return msgs || `Request failed (${result.status})`;
    }
    case "forbidden":
      return "You do not have permission to perform this action.";
    case "unauthenticated":
      return "Your session has expired. Please sign in again.";
    case "network_error":
      return "Could not reach the server. Please try again.";
    default:
      return "An unexpected error occurred.";
  }
}
