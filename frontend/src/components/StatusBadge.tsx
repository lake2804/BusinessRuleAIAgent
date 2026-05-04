export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const color =
    normalized === "active" || normalized === "succeeded"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : normalized === "running" || normalized === "queued"
        ? "bg-blue-50 text-blue-700 ring-blue-200"
        : normalized === "failed"
          ? "bg-rose-50 text-rose-700 ring-rose-200"
          : "bg-slate-100 text-slate-700 ring-slate-200";
  return <span className={`rounded-full px-2 py-1 text-xs font-medium ring-1 ${color}`}>{status}</span>;
}
