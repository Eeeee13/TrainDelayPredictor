import { RiskLevel } from "@/domain/types";
import { useDashboardStore } from "@/store/dashboardStore";

const RISK_OPTIONS: { value: RiskLevel; label: string; dot: string }[] = [
  { value: "low", label: "Низкий", dot: "bg-risk-low" },
  { value: "medium", label: "Средний", dot: "bg-risk-mid" },
  { value: "high", label: "Высокий", dot: "bg-risk-high" }
];

export function FilterBar() {
  const filters = useDashboardStore((s) => s.filters);
  const setFilters = useDashboardStore((s) => s.setFilters);

  const toggleRisk = (level: RiskLevel) => {
    const current = filters.riskLevels ?? [];
    const next = current.includes(level)
      ? current.filter((l) => l !== level)
      : [...current, level];
    setFilters({ riskLevels: next.length ? next : null });
  };

  return (
    <div className="flex items-center gap-1.5">
      {RISK_OPTIONS.map((opt) => {
        const active = filters.riskLevels?.includes(opt.value) ?? false;
        return (
          <button
            key={opt.value}
            onClick={() => toggleRisk(opt.value)}
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] transition-colors ${
              active ? "bg-base-700 dark:bg-base-700 bg-gray-300 text-base-200 dark:text-base-200 text-gray-800" : "text-base-400 dark:text-base-400 text-gray-600 hover:bg-base-800 dark:hover:bg-base-800 hover:bg-gray-200"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${opt.dot}`} />
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
