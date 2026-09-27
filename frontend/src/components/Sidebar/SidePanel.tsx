import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusList } from "./BusList";
import { FilterBar } from "@/components/Filters/FilterBar";
import { NotificationToggle } from "@/components/Map/Notifications";
import { isAhead } from "@/utils/riskLabel";
import { stopLabel } from "@/utils/stopLabel";

type Tab = "buses" | "alerts";

const severityRank: Record<string, number> = { high: 2, medium: 1 };

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("buses");
  const vehicles = useDashboardStore((s) => s.vehicles);
  const routes = useDashboardStore((s) => s.routes);
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);
  const query = useDashboardStore((s) => s.filters.query);
  const setFilters = useDashboardStore((s) => s.setFilters);
  const alerts = Object.values(vehicles)
    .filter(v => v.risk === "high" || v.risk === "medium")
    .sort((a, b) => (severityRank[b.risk!] - severityRank[a.risk!]) || (b.predictedDelaySeconds ?? 0) - (a.predictedDelaySeconds ?? 0));

  return (
    <div className="pointer-events-auto flex flex-col h-full rounded-2xl bg-white/90 backdrop-blur-xl border border-gray-200 shadow-panel overflow-hidden">
      <div className="flex items-center gap-1 px-2.5 pt-2.5">
        <div className="flex items-center gap-0.5 bg-gray-100 rounded-full p-0.5 w-full">
          <button
            onClick={() => setTab("buses")}
            className={`flex-1 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              tab === "buses" ? "bg-gray-300 text-gray-800" : "text-gray-600"
            }`}
          >
            ТС
          </button>
          <button
            onClick={() => setTab("alerts")}
            className={`flex-1 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              tab === "alerts" ? "bg-gray-300 text-gray-800" : "text-gray-600"
            }`}
          >
            Алерты
            {alerts.length > 0 && (
              <span className="ml-1.5 text-[10px] text-gray-600">{alerts.length}</span>
            )}
          </button>
        </div>
      </div>

      {tab === "buses" && (
        <div className="px-2.5 pt-2 space-y-2">
          <div className="relative">
            <input
              type="search"
              value={query}
              onChange={(event) => setFilters({ query: event.target.value })}
              placeholder="Поиск по борту"
              aria-label="Поиск по борту"
              className="w-full rounded-xl bg-gray-100 py-1.5 pl-3 pr-7 text-xs text-gray-800 outline-none placeholder:text-gray-500 focus:ring-1 focus:ring-gray-300 [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button
                type="button"
                onClick={() => setFilters({ query: "" })}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs leading-none text-gray-500 hover:text-gray-800"
                aria-label="Очистить поиск"
              >
                ✕
              </button>
            )}
          </div>
          <FilterBar />
        </div>
      )}

      <div className="flex-1 min-h-0 mt-1">
        {tab === "buses" ? <BusList /> : (
          <div className="flex flex-col h-full min-h-0">
            <div className="px-2.5 py-2 border-b border-gray-100 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">
                {alerts.length} {alerts.length === 1 ? "алерт" : alerts.length > 1 && alerts.length < 5 ? "алерта" : "алертов"}
              </span>
              <NotificationToggle />
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-1">
              {alerts.length ? alerts.map(v => {
              const route = routes.find(r => r.id === v.routeId);
              const target = route?.stops.find(s => s.id === v.targetStopId);
              return (
                <button
                  key={v.id}
                  onClick={() => selectVehicle(v.id)}
                  className={`w-full flex gap-2.5 items-start text-left p-2.5 rounded-xl transition-colors ${
                    v.id === selectedVehicleId ? "bg-gray-200" : "bg-gray-100 hover:bg-gray-200"
                  }`}
                >
                  <span className={`h-2 w-2 rounded-full mt-1.5 flex-none ${v.risk === "high" ? "bg-risk-high" : "bg-risk-mid"}`} />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-gray-800 truncate">
                      Борт {v.garageNumber}{route?.shortName ? ` · Маршрут ${route.shortName}` : ""}
                    </div>
                    <p className="mt-1 text-xs text-gray-600">
                      {isAhead(v.predictedDelaySeconds)
                        ? `Прогноз опережения ${Math.abs(Math.round((v.predictedDelaySeconds ?? 0) / 60))} мин`
                        : `Прогноз опоздания +${Math.round((v.predictedDelaySeconds ?? 0) / 60)} мин`}
                    </p>
                    {target && (
                      <p className="mt-0.5 text-[11px] text-gray-500 break-words">До остановки {stopLabel(target)}</p>
                    )}
                  </div>
                </button>
              );
            }) : (
              <div className="text-sm text-gray-600 px-3 py-6 text-center">Активных алертов нет</div>
            )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}