import { useDashboardStore } from "@/store/dashboardStore";
export function KpiBar() {
  const kpi = useDashboardStore(s => s.kpi);
  const predictedCount = Object.values(useDashboardStore(s => s.vehicles)).filter(v => v.predictedDelaySeconds !== null).length;
  return <div className="kpis">
    <div className="kpi"><strong>{predictedCount ? `${kpi.onTimePct}%` : "—"}</strong><span>по графику</span></div>
    <div className="kpi"><strong className="amber">{predictedCount ? `${kpi.atRiskPct}%` : "—"}</strong><span>в риске</span></div>
    <div className="kpi"><strong>{predictedCount ? `${Math.round(kpi.avgPredictedDelaySec / 60)} мин` : "—"}</strong><span>ср. отклонение</span></div>
  </div>;
}
