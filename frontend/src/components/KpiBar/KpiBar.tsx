import { useDashboardStore } from "@/store/dashboardStore";

function Pill({ value, label, tone }: { value: string; label: string; tone?: "risk" }) {
  return (
    <div className="flex items-baseline gap-1.5 px-3 first:pl-0 last:pr-0">
      <span className={`text-[15px] font-semibold tabular-nums ${tone === "risk" ? "text-risk-mid" : "text-base-200 dark:text-base-200 text-gray-800"}`}>
        {value}
      </span>
      <span className="text-[11px] text-base-400 dark:text-base-400 text-gray-600">{label}</span>
    </div>
  );
}

export function KpiBar() {
  const kpi = useDashboardStore((s) => s.kpi);
  const theme = useDashboardStore((s) => s.theme);
  const toggleTheme = useDashboardStore((s) => s.toggleTheme);

  return (
    <div className="flex items-center divide-x divide-base-700/60">
      <Pill value={`${kpi.onTimePct}%`} label="по графику" />
      <Pill value={`${kpi.atRiskPct}%`} label="в риске" tone="risk" />
      <Pill value={`${Math.round(kpi.avgPredictedDelaySec / 60)} мин`} label="ср. отклонение" />
      <Pill value={String(kpi.activeAlerts)} label="алёртов" />
      <button
        onClick={toggleTheme}
        className="ml-4 p-2 rounded-lg hover:bg-base-800/50 dark:hover:bg-base-800/50 hover:bg-gray-200 transition-colors"
        title={theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"}
      >
        {theme === "dark" ? (
          <svg className="w-5 h-5 text-base-200 dark:text-base-200 text-gray-800" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ) : (
          <svg className="w-5 h-5 text-base-200 dark:text-base-200 text-gray-800" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        )}
      </button>
    </div>
  );
}
