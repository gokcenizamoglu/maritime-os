"use client";

import { useState } from "react";
import { ApiErrorState } from "@/components/feedback/ApiErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { WorkflowStepStatusBadge } from "@/components/workflow/WorkflowStepStatusBadge";
import type { ApiResult } from "@/lib/api/result";
import type { ChecklistItem } from "@/types/checklist";
import type { DocumentRecord } from "@/types/document";
import type { ServiceRequestDetail } from "@/types/service-request";
import type { TimelineEntry } from "@/types/timeline";
import type { WorkflowStepInstance } from "@/types/workflow";
import { StatusBadge } from "./StatusBadge";

const TABS = ["Overview", "Documents", "Checklist", "Workflow", "Activity"] as const;
type TabName = (typeof TABS)[number];

interface ServiceRequestTabsProps {
  detail: ServiceRequestDetail;
  timeline: ApiResult<TimelineEntry[]>;
  checklist: ApiResult<ChecklistItem[]>;
  workflow: ApiResult<WorkflowStepInstance[]>;
  documents: ApiResult<DocumentRecord[]>;
}

/**
 * Tab switching is client-side state (no URL segments per tab) — data for
 * every tab is fetched once, server-side, by the parent Server Component
 * page and passed down as props, so switching tabs never triggers a
 * network request. See docs/FRONTEND_INFORMATION_ARCHITECTURE.md §5.
 */
export function ServiceRequestTabs({ detail, timeline, checklist, workflow, documents }: ServiceRequestTabsProps) {
  const [active, setActive] = useState<TabName>("Overview");

  return (
    <div>
      <div role="tablist" aria-label="Service request sections" className="flex gap-1 border-b border-black/[.08]">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active === tab}
            onClick={() => setActive(tab)}
            className={`px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ${
              active === tab
                ? "border-b-2 border-zinc-900 text-zinc-900"
                : "text-zinc-500 hover:text-zinc-700"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="pt-4">
        {active === "Overview" && <OverviewTab detail={detail} />}
        {active === "Documents" && <DocumentsTab result={documents} />}
        {active === "Checklist" && <ChecklistTab result={checklist} />}
        {active === "Workflow" && <WorkflowTab result={workflow} />}
        {active === "Activity" && <ActivityTab result={timeline} />}
      </div>
    </div>
  );
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-zinc-900">{children}</dd>
    </div>
  );
}

function OverviewTab({ detail }: { detail: ServiceRequestDetail }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
      <Field label="Status">
        <StatusBadge status={detail.status} />
      </Field>
      <Field label="Created">{formatDateTime(detail.created_at)}</Field>
      <Field label="Updated">{formatDateTime(detail.updated_at)}</Field>
      <Field label="Checklist progress">
        {detail.checklist_progress.complete}/{detail.checklist_progress.total} (
        {detail.checklist_progress.percent}%)
      </Field>
      <Field label="Customer">#{detail.customer}</Field>
      <Field label="Vessel">#{detail.vessel}</Field>
      <Field label="Service Type">{detail.service_offering_summary?.service_type ?? `#${detail.service_type}`}</Field>
      <Field label="Flag">
        {detail.service_offering_summary?.flag ?? (detail.flag ? `#${detail.flag}` : "Not applicable")}
      </Field>
      <Field label="Offering">{detail.service_offering_summary?.display_name ?? "Legacy operation"}</Field>
      <Field label="Process version">
        {detail.operation_template_summary
          ? `${detail.operation_template_summary.code} v${detail.operation_template_summary.version_number}`
          : "Legacy template"}
      </Field>
    </dl>
  );
}

function DocumentsTab({ result }: { result: ApiResult<DocumentRecord[]> }) {
  if (!result.ok) return <ApiErrorState result={result} />;
  if (result.data.length === 0) return <EmptyState title="No documents" />;
  return (
    <ul className="flex flex-col gap-2">
      {result.data.map((document) => (
        <li key={document.id} className="flex items-center justify-between rounded-md border border-black/[.08] px-3 py-2 text-sm">
          <span>
            <span className="block text-zinc-900">{document.original_filename}</span>
            <span className="text-xs text-zinc-500">{document.document_type_name ?? "Unclassified"}</span>
          </span>
          <Badge tone={document.is_superseded ? "neutral" : document.status === "validated" ? "success" : "neutral"}>
            {document.is_superseded ? "Superseded" : document.status}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function ChecklistTab({ result }: { result: ApiResult<ChecklistItem[]> }) {
  if (!result.ok) return <ApiErrorState result={result} />;
  if (result.data.length === 0) return <EmptyState title="No checklist items" />;
  return (
    <ul className="flex flex-col gap-2">
      {result.data.map((item) => (
        <li
          key={item.id}
          className="flex items-center justify-between rounded-md border border-black/[.08] px-3 py-2 text-sm"
        >
          <span>{item.document_type_name}</span>
          <span className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">
              {item.mapped_document_count}/{item.required_count}
            </span>
            <Badge tone={item.is_complete ? "success" : "neutral"}>
              {item.is_complete ? "Complete" : "Incomplete"}
            </Badge>
          </span>
        </li>
      ))}
    </ul>
  );
}

function WorkflowTab({ result }: { result: ApiResult<WorkflowStepInstance[]> }) {
  if (!result.ok) return <ApiErrorState result={result} />;
  if (result.data.length === 0) return <EmptyState title="No workflow steps" />;
  return (
    <ul className="flex flex-col gap-2">
      {result.data.map((step) => (
        <li
          key={step.id}
          className="flex items-center justify-between rounded-md border border-black/[.08] px-3 py-2 text-sm"
        >
          <span>{step.step_name}</span>
          <WorkflowStepStatusBadge status={step.status} />
        </li>
      ))}
    </ul>
  );
}

function ActivityTab({ result }: { result: ApiResult<TimelineEntry[]> }) {
  if (!result.ok) return <ApiErrorState result={result} />;
  if (result.data.length === 0) return <EmptyState title="No activity yet" />;
  return (
    <ul className="flex flex-col gap-3">
      {result.data.map((entry) => (
        <li key={entry.id} className="border-b border-black/[.06] pb-3 last:border-0">
          <p className="text-sm text-zinc-900">{entry.summary}</p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {entry.actor.name ?? entry.actor.type} · {formatDateTime(entry.timestamp)}
          </p>
        </li>
      ))}
    </ul>
  );
}
