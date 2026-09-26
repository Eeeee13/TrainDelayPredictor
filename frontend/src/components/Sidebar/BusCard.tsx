import { RouteDef, Vehicle } from "@/domain/types";
import { BusSideIcon } from "./BusSideIcon";

const RISK_TEXT: Record<Exclude<Vehicle["risk"], null>, string> = {
  low: "по графику",
  medium: "небольшое отставание",
  high: "риск опоздания"
};

interface Props {
  vehicle: Vehicle;
  route?: RouteDef;
  selected: boolean;
  onSelect: () => void;
}

export function BusCard({ vehicle, route, selected, onSelect }: Props) {
  const minutes = vehicle.predictedDelaySeconds !== null ? Math.round(vehicle.predictedDelaySeconds / 60) : 0;
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-xl px-3 py-2.5 flex items-center gap-3 transition-colors border ${
        selected
          ? "bg-gray-200 border-gray-400"
          : "border-transparent hover:bg-gray-100"
      }`}
    >
      <BusSideIcon risk={vehicle.risk ?? "low"} number={route?.shortName ?? "–"} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-gray-800 truncate">
            Борт {vehicle.garageNumber} · Маршрут {route?.shortName}
          </span>
        </div>
        <div className="text-xs text-gray-600 truncate">{vehicle.risk ? RISK_TEXT[vehicle.risk] : "Ожидает прогноза"}</div>
        {vehicle.delayProbability != null && (
          <div className="text-[10px] text-gray-600 tabular-nums mt-0.5">
            Вероятность &gt;2 мин: {Math.round(vehicle.delayProbability * 100)}%
          </div>
        )}
      </div>
      {minutes > 0 && (
        <div className="text-xs font-semibold text-risk-high tabular-nums shrink-0">
          +{minutes} мин
        </div>
      )}
    </button>
  );
}
