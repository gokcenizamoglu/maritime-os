export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-black/[.12] p-10 text-center">
      <p className="text-sm font-medium text-zinc-900">{title}</p>
      {description && <p className="mt-1 text-sm text-zinc-500">{description}</p>}
    </div>
  );
}
