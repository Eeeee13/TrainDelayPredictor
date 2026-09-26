import { useDashboardStore } from "@/store/dashboardStore";

function Pill({ value, label, tone }: { value: string; label: string; tone?: "risk" }) {
  return (
    <div className="flex items-baseline gap-1.5 px-3 first:pl-0 last:pr-0">
      <span className={`text-[15px] font-semibold tabular-nums ${tone === "risk" ? "text-risk-mid" : "text-gray-800"}`}>
        {value}
      </span>
      <span className="text-[11px] text-gray-600">{label}</span>
    </div>
  );
}

export function KpiBar() {
  const kpi = useDashboardStore((s) => s.kpi);
  const predictedCount = Object.values(useDashboardStore((s) => s.vehicles)).filter(v => v.predictedDelaySeconds !== null).length;

  return (
    <div className="flex items-center divide-x divide-gray-300">
      <Pill value={predictedCount ? `${kpi.onTimePct}%` : "—"} label="по графику" />
      <Pill value={predictedCount ? `${kpi.atRiskPct}%` : "—"} label="в риске" tone="risk" />
      <Pill value={predictedCount ? `${Math.round(kpi.avgPredictedDelaySec / 60)} мин` : "—"} label="ср. отклонение" />
    </div>
  );
}
