import { RouteDef, Vehicle } from "@/domain/types";
import { BusSideIcon } from "./BusSideIcon";

const RISK_TEXT: Record<Vehicle["risk"], string> = {
  low: "по графику",
  mid: "небольшое отставание",
  high: "риск опоздания"
};

interface Props {
  vehicle: Vehicle;
  route?: RouteDef;
  selected: boolean;
  onSelect: () => void;
}

export function BusCard({ vehicle, route, selected, onSelect }: Props) {
  const minutes = Math.round(vehicle.predictedDelaySeconds / 60);
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-xl px-3 py-2.5 flex items-center gap-3 transition-colors border ${
        selected
          ? "bg-base-800 dark:bg-base-800 bg-gray-200 border-base-600 dark:border-base-600 border-gray-400"
          : "border-transparent hover:bg-base-900 dark:hover:bg-base-900 hover:bg-gray-100"
      }`}
    >
      <BusSideIcon risk={vehicle.risk} number={route?.shortName ?? "–"} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-base-200 dark:text-base-200 text-gray-800 truncate">
            Маршрут {route?.shortName} · №{vehicle.garageNumber}
          </span>
        </div>
        <div className="text-xs text-base-400 dark:text-base-400 text-gray-600 truncate">{RISK_TEXT[vehicle.risk]}</div>
      </div>
      {minutes > 0 && (
        <div className="text-xs font-semibold text-risk-high tabular-nums shrink-0">
          +{minutes} мин
        </div>
      )}
    </button>
  );
}
