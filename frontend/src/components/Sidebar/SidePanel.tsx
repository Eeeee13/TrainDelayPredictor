import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusList } from "./BusList";
import { AlertsFeed } from "@/components/Alerts/AlertsFeed";
import { FilterBar } from "@/components/Filters/FilterBar";

type Tab = "buses" | "alerts";

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("buses");
  const selectedRouteId = useDashboardStore((s) => s.selectedRouteId);
  const selectRoute = useDashboardStore((s) => s.selectRoute);
  const routes = useDashboardStore((s) => s.routes);
  const alertsCount = useDashboardStore((s) => s.alerts.length);

  const selectedRoute = routes.find((r) => r.id === selectedRouteId);

  return (
    <div className="pointer-events-auto flex flex-col h-full rounded-2xl bg-base-900/75 dark:bg-base-900/75 bg-white/90 backdrop-blur-xl border border-white/[0.06] dark:border-white/[0.06] border-gray-200 shadow-panel overflow-hidden">
      <div className="flex items-center gap-1 px-2.5 pt-2.5">
        <div className="flex items-center gap-0.5 bg-base-800/70 dark:bg-base-800/70 bg-gray-100 rounded-full p-0.5">
          <button
            onClick={() => setTab("buses")}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              tab === "buses" ? "bg-base-600 dark:bg-base-600 bg-gray-300 text-base-200 dark:text-base-200 text-gray-800" : "text-base-400 dark:text-base-400 text-gray-600"
            }`}
          >
            ТС
          </button>
          <button
            onClick={() => setTab("alerts")}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors relative ${
              tab === "alerts" ? "bg-base-600 dark:bg-base-600 bg-gray-300 text-base-200 dark:text-base-200 text-gray-800" : "text-base-400 dark:text-base-400 text-gray-600"
            }`}
          >
            Алёрты
            {alertsCount > 0 && (
              <span className="ml-1.5 text-[10px] text-base-400 dark:text-base-400 text-gray-600">{alertsCount}</span>
            )}
          </button>
        </div>
      </div>

      {selectedRoute && (
        <div className="flex items-center justify-between px-3.5 pt-2">
          <span className="text-xs text-base-300 dark:text-base-300 text-gray-700 flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: selectedRoute.color }}
            />
            Маршрут {selectedRoute.shortName}
          </span>
          <button
            onClick={() => selectRoute(null)}
            className="text-[11px] text-accent hover:opacity-80"
          >
            Сбросить
          </button>
        </div>
      )}

      {tab === "buses" && (
        <div className="px-2.5 pt-2">
          <FilterBar />
        </div>
      )}

      <div className="flex-1 min-h-0 mt-1">
        {tab === "buses" ? <BusList /> : <AlertsFeed />}
      </div>
    </div>
  );
}
