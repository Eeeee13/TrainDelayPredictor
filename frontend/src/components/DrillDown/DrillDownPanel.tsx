import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { getBusVariant } from "@/utils/busVariant";
import busV1Front from "../../assets/bus-v1-front.png";
import busV2Front from "../../assets/bus-v2-front.png";
import { incidentTitle } from "@/utils/riskLabel";
import { stopLabel } from "@/utils/stopLabel";

export function DrillDownPanel() {
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);
  const vehicle = useDashboardStore((s) =>
    selectedVehicleId ? s.vehicles[selectedVehicleId] : undefined
  );
  const route = useDashboardStore((s) =>
    vehicle ? s.routes.find((r) => r.id === vehicle.routeId) : undefined
  );
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);
  const [reportState, setReportState] = useState<"idle" | "loading" | "error">("idle");
  const [reportError, setReportError] = useState<string | null>(null);

  if (!vehicle) return null;

  async function generateReport() {
    setReportState("loading");
    setReportError(null);
    try {
      const response = await fetch(`/vehicles/${encodeURIComponent(vehicle.id)}/report`, { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `report-${vehicle.id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      setReportState("idle");
    } catch (error) {
      setReportState("error");
      setReportError(error instanceof Error ? error.message : "Не удалось сформировать отчёт");
    }
  }

  const variant = getBusVariant(vehicle.id);
  const busFrontImage = variant === "v1" ? busV1Front : busV2Front;
  const minutes = vehicle.predictedDelaySeconds !== null ? Math.round(vehicle.predictedDelaySeconds / 60) : 0;
  const factMinutes = vehicle.delaySeconds !== null ? Math.round(vehicle.delaySeconds / 60) : 0;
  const target = route?.stops.find(s => s.id === vehicle.targetStopId);

  return (
    <div className="pointer-events-auto h-full w-[320px] rounded-2xl bg-white/90 backdrop-blur-xl border border-white/[0.06] dark:border-white/[0.06] border-gray-200 shadow-panel flex flex-col overflow-hidden animate-[fadeIn_0.15s_ease-out]">
      <div className="relative h-[132px] overflow-hidden border-b border-gray-200">
        <img
          src={busFrontImage}
          alt=""
          className="pointer-events-none absolute left-1/2 top-[42%] w-[160px] max-w-none -translate-x-1/2 -translate-y-1/2"
        />
        <button
          onClick={() => selectVehicle(null)}
          className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-white/90 text-sm leading-none text-gray-700 shadow-sm"
          aria-label="Закрыть"
        >
          ✕
        </button>
        <div className="absolute bottom-2 left-1/2 z-10 flex -translate-x-1/2 items-center rounded-[3px] border-2 border-black bg-white px-2 py-1 shadow-md">
          <span className="text-[15px] font-bold leading-none tracking-wide text-black">
            Борт №{vehicle.garageNumber}
          </span>
        </div>
      </div>

      {(vehicle.risk === "high" || vehicle.risk === "medium") && (
        <div
          className={`px-4 py-2 border-b text-xs font-semibold uppercase tracking-wide ${
            vehicle.risk === "high"
              ? "bg-risk-high/10 border-risk-high/20 text-risk-high"
              : "bg-risk-mid/10 border-risk-mid/20 text-risk-mid"
          }`}
        >
          {incidentTitle(vehicle.risk, vehicle.predictedDelaySeconds)}
        </div>
      )}

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
          {vehicle.delayProbability != null && (
            <div className="text-[10px] text-gray-600 tabular-nums mt-0.5">
              Вероятность &gt;2 мин: {Math.round(vehicle.delayProbability * 100)}%
            </div>
          )}
        </div>
      </div>

      <div className="px-4 pb-3 border-b border-gray-200">
        <button
          type="button"
          onClick={() => { void generateReport(); }}
          disabled={reportState === "loading"}
          className="w-full rounded-xl bg-gray-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {reportState === "loading" ? "Формируем отчёт…" : "Сгенерировать отчёт"}
        </button>
        {reportError && <p className="mt-2 text-xs text-risk-high">{reportError}</p>}
      </div>

      <div className="flex-1 overflow-y-auto">
      <div className="px-4 py-3">
        <div className="text-[10px] uppercase text-gray-600 mb-1.5">Проблемный участок</div>
        <div className="text-sm text-gray-800 break-words">
          {target ? `До остановки ${stopLabel(target)}` : "Целевая остановка пока не определена"}
        </div>
        <div className="text-xs text-gray-600 mt-1">
          {vehicle.targetTime ? `Плановое прибытие: ${new Date(vehicle.targetTime).toLocaleString("ru-RU")}` : "Прогноз появится при входе в горизонт 10–15 минут"}
        </div>
        {(vehicle.risk === "high" || vehicle.risk === "medium") && (
          <div className="text-xs text-gray-600 mt-1">
            Причина: {vehicle.reason ?? "не определена моделью"}
          </div>
        )}
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
            <div key={stop.id} className={`flex justify-between gap-2 text-xs ${stop.id === vehicle.targetStopId ? "text-risk-high font-semibold" : "text-gray-600"}`}>
              <span className="min-w-0 truncate">{stopLabel(stop)}</span>
              <time>{new Date(stop.scheduledTime).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</time>
            </div>
          ))}
        </div>
      </div>
      </div>
    </div>
  );
}
