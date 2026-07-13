export default function RulesPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Rules</h1>
      <p className="mt-2 max-w-xl text-sm text-zinc-600">
        Not connected in this slice. The backend already exposes <code>/api/rules/</code> and{" "}
        <code>/api/rules/metadata/</code>, but building the Rules UI is out of scope for this
        implementation slice — see docs/FRONTEND_INFORMATION_ARCHITECTURE.md.
      </p>
    </div>
  );
}
