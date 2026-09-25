import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid
} from "recharts";
import { useDashboardStore } from "@/store/dashboardStore";

export function DrillDownPanel() {
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);
  const vehicle = useDashboardStore((s) =>
    selectedVehicleId ? s.vehicles[selectedVehicleId] : undefined
  );
  const route = useDashboardStore((s) =>
    vehicle ? s.routes.find((r) => r.id === vehicle.routeId) : undefined
  );
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);

  if (!vehicle) return null;

  const minutes = Math.round(vehicle.predictedDelaySeconds / 60);
  const factMinutes = Math.round(vehicle.delaySeconds / 60);

  return (
    <div className="pointer-events-auto h-full w-[320px] rounded-2xl bg-base-900/80 dark:bg-base-900/80 bg-white/90 backdrop-blur-xl border border-white/[0.06] dark:border-white/[0.06] border-gray-200 shadow-panel flex flex-col overflow-hidden animate-[fadeIn_0.15s_ease-out]">
      <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-base-800 dark:border-base-800 border-gray-200">
        <div>
          <div className="text-sm font-semibold text-base-200 dark:text-base-200 text-gray-800">
            Маршрут {route?.shortName} · Борт №{vehicle.garageNumber}
          </div>
          <div className="text-xs text-base-400 dark:text-base-400 text-gray-600 mt-0.5">{route?.longName}</div>
        </div>
        <button
          onClick={() => selectVehicle(null)}
          className="text-base-400 dark:text-base-400 text-gray-600 hover:text-base-200 dark:hover:text-base-200 hover:text-gray-800 text-sm leading-none px-1"
          aria-label="Закрыть"
        >
          ✕
        </button>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-base-850 dark:bg-base-850 bg-gray-100 px-3 py-2">
          <div className="text-[10px] uppercase text-base-400 dark:text-base-400 text-gray-600">Факт. отклонение</div>
          <div className="text-lg font-semibold text-base-200 dark:text-base-200 text-gray-800">{factMinutes} мин</div>
        </div>
        <div className="rounded-xl bg-base-850 dark:bg-base-850 bg-gray-100 px-3 py-2">
          <div className="text-[10px] uppercase text-base-400 dark:text-base-400 text-gray-600">Прогноз ({vehicle.predictedHorizonMinutes} мин)</div>
          <div
            className={`text-lg font-semibold ${
              vehicle.risk === "high"
                ? "text-risk-high"
                : vehicle.risk === "mid"
                ? "text-risk-mid"
                : "text-risk-low"
            }`}
          >
            {minutes} мин
          </div>
        </div>
      </div>

      <div className="px-2 flex-1 min-h-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={vehicle.schedule} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            <CartesianGrid stroke="#26262c" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="t" tick={{ fill: "#8a8a93", fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: "#8a8a93", fontSize: 10 }} tickLine={false} axisLine={false} width={30} />
            <Tooltip
              contentStyle={{
                background: "#1c1c21",
                border: "1px solid #26262c",
                borderRadius: 10,
                fontSize: 12
              }}
              labelStyle={{ color: "#8a8a93" }}
            />
            <Line type="monotone" dataKey="planned" stroke="#8a8a93" strokeWidth={1.5} dot={false} name="План" />
            <Line type="monotone" dataKey="actual" stroke="#0a84ff" strokeWidth={2} dot={false} name="Факт" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="px-4 py-3 border-t border-base-800 dark:border-base-800 border-gray-200">
        <div className="text-[10px] uppercase text-base-400 dark:text-base-400 text-gray-600 mb-1.5">Остановки маршрута</div>
        <div className="flex flex-wrap gap-1">
          {route?.stops.slice(0, 8).map((stop) => (
            <span
              key={stop.id}
              className="text-[10px] px-1.5 py-0.5 rounded bg-base-850 dark:bg-base-850 bg-gray-100 text-base-400 dark:text-base-400 text-gray-600"
            >
              {stop.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
