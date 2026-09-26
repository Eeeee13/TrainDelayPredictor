import { useDashboardStore } from "@/store/dashboardStore";
import { getBusVariant } from "@/utils/busVariant";
import busV1Front from "../../assets/bus-v1-front.png";
import busV2Front from "../../assets/bus-v2-front.png";

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

  const variant = getBusVariant(vehicle.id);
  const busFrontImage = variant === "v1" ? busV1Front : busV2Front;
  const minutes = vehicle.predictedDelaySeconds !== null ? Math.round(vehicle.predictedDelaySeconds / 60) : 0;
  const factMinutes = vehicle.delaySeconds !== null ? Math.round(vehicle.delaySeconds / 60) : 0;
  const target = route?.stops.find(s => s.id === vehicle.targetStopId);

  return (
    <div className="pointer-events-auto h-full w-[320px] rounded-2xl bg-white/90 backdrop-blur-xl border border-white/[0.06] dark:border-white/[0.06] border-gray-200 shadow-panel flex flex-col overflow-hidden animate-[fadeIn_0.15s_ease-out]">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3 border-b border-gray-200">
        <img 
          src={busFrontImage} 
          alt={`Bus ${vehicle.garageNumber}`} 
          className="w-20 h-16 object-contain flex-shrink-0" 
        />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-gray-800 truncate">
            Борт №{vehicle.garageNumber}
          </div>
          <div className="text-xs text-gray-600 truncate">Маршрут {route?.shortName}</div>
        </div>
        <button
          onClick={() => selectVehicle(null)}
          className="text-gray-600 hover:text-gray-800 text-sm leading-none px-1 flex-shrink-0"
          aria-label="Закрыть"
        >
          ✕
        </button>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-gray-100 px-3 py-2">
          <div className="text-[10px] uppercase text-gray-600">Факт. отклонение</div>
          <div className="text-lg font-semibold  text-gray-800">{factMinutes} мин</div>
        </div>
        <div className="rounded-xl bg-gray-100 px-3 py-2">
          <div className="text-[10px] uppercase text-gray-600">Прогноз (10-15 мин)</div>
          <div
            className={`text-lg font-semibold ${
              vehicle.risk === "high"
                ? "text-risk-high"
                : vehicle.risk === "medium"
                ? "text-risk-mid"
                : "text-risk-low"
            }`}
          >
            {minutes > 0 ? `+${minutes}` : minutes} мин
          </div>
        </div>
      </div>

      <div className="px-4 py-3 border-t border-gray-200">
        <div className="text-[10px] uppercase text-gray-600 mb-1.5">Проблемный участок</div>
        <div className="text-sm  text-gray-800">
          {target ? `До остановки №${target.sequence}` : "Целевая остановка пока не определена"}
        </div>
        <div className="text-xs text-gray-600 mt-1">
          {vehicle.targetTime ? `Плановое прибытие: ${new Date(vehicle.targetTime).toLocaleString("ru-RU")}` : "Прогноз появится при входе в горизонт 10–15 минут"}
        </div>
      </div>

      <div className="px-4 py-3 border-t border-gray-200">
        <div className="text-[10px] uppercase text-gray-600 mb-1.5">Последняя телеметрия</div>
        <div className="text-sm  text-gray-800">
          {new Date(vehicle.lastUpdate).toLocaleString("ru-RU")}
        </div>
        <div className="text-xs text-gray-600 mt-1">
          Скорость {Math.round(vehicle.speedKmh)} км/ч · Источник {vehicle.source ?? "GPS"}
        </div>
      </div>

      <div className="px-4 py-3 border-t border-gray-200">
        <div className="text-[10px] uppercase text-gray-600 mb-1.5">Ближайшие остановки</div>
        <div className="flex flex-col gap-1">
          {route?.stops.slice(0, 5).map((stop) => (
            <div key={stop.id} className={`flex justify-between text-xs ${stop.id === vehicle.targetStopId ? "text-risk-high font-semibold" : "text-gray-600"}`}>
              <span>№{stop.sequence}</span>
              <time>{new Date(stop.scheduledTime).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</time>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
