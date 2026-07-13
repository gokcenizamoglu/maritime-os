interface RuleDetailPageProps {
  params: Promise<{ ruleId: string }>;
}

export default async function RuleDetailPage({ params }: RuleDetailPageProps) {
  const { ruleId } = await params;
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Rule #{ruleId}</h1>
      <p className="mt-2 max-w-xl text-sm text-zinc-600">
        Not connected in this slice — see docs/FRONTEND_INFORMATION_ARCHITECTURE.md.
      </p>
    </div>
  );
}
