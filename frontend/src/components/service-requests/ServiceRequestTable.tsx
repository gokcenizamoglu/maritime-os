import Link from "next/link";
import { StatusBadge } from "./StatusBadge";
import type { ServiceRequestListItem } from "@/types/service-request";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function ServiceRequestTable({ items }: { items: ServiceRequestListItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-black/[.08]">
      <table className="w-full text-left text-[13px]">
        <thead className="border-b border-black/[.08] bg-zinc-50 text-xs text-zinc-500">
          <tr>
            <th className="px-3 py-2 font-medium">Reference</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Customer</th>
            <th className="px-3 py-2 font-medium">Vessel</th>
            <th className="px-3 py-2 font-medium">Service Type</th>
            <th className="px-3 py-2 font-medium">Flag</th>
            <th className="px-3 py-2 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-black/[.06] last:border-0 hover:bg-zinc-50">
              <td className="px-3 py-2">
                <Link
                  href={`/operations/${item.id}`}
                  className="font-medium text-zinc-900 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
                >
                  {item.reference_code}
                </Link>
              </td>
              <td className="px-3 py-2">
                <StatusBadge status={item.status} />
              </td>
              <td className="px-3 py-2 text-zinc-700">{item.customer_name}</td>
              <td className="px-3 py-2 text-zinc-700">{item.vessel_name}</td>
              <td className="px-3 py-2 text-zinc-700">{item.service_type_name}</td>
              <td className="px-3 py-2 text-zinc-700">{item.flag_name ?? "Not applicable"}</td>
              <td className="px-3 py-2 text-zinc-500">{formatDate(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
