import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusList } from "./BusList";
import { FilterBar } from "@/components/Filters/FilterBar";

type Tab = "buses" | "alerts";

export function SidePanel() {
  const [tab, setTab] = useState<Tab>("buses");
  const vehicles = useDashboardStore((s) => s.vehicles);
  const alerts = Object.values(vehicles).filter(v => v.risk === "high" || v.risk === "medium");

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
        <div className="px-2.5 pt-2">
          <FilterBar />
        </div>
      )}

      <div className="flex-1 min-h-0 mt-1">
        {tab === "buses" ? <BusList /> : (
          <div className="flex flex-col h-full min-h-0 overflow-y-auto px-2 py-2 space-y-1">
            {alerts.length ? alerts.map(v => (
              <div key={v.id} className="flex gap-2.5 items-start bg-gray-100 p-2.5 rounded-xl">
                <span className={`h-2 w-2 rounded-full mt-1.5 flex-none ${v.risk === "high" ? "bg-risk-high" : "bg-risk-mid"}`} />
                <div>
                  <div className="text-sm font-semibold text-gray-800">Борт {v.garageNumber}</div>
                  <p className="mt-1 text-xs text-gray-600">Прогноз опоздания +{Math.round((v.predictedDelaySeconds ?? 0) / 60)} мин</p>
                </div>
              </div>
            )) : (
              <div className="text-sm text-gray-600 px-3 py-6 text-center">Активных алертов нет</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
