import busV1Side from "../../assets/bus-v1-side.png";
import busV2Side from "../../assets/bus-v2-side.png";
import { RiskLevel } from "@/domain/types";
import { getBusVariant } from "@/utils/busVariant";

const RISK_COLOR: Record<RiskLevel, string> = {
  low: "#30d158",
  medium: "#ffd60a",
  high: "#ff453a",
};

interface Props {
  risk: RiskLevel;
  number: string;
  vehicleId: string;
}


export function BusSideIcon({ risk, number, vehicleId }: Props) {
  const color = RISK_COLOR[risk];
  const variant = getBusVariant(vehicleId);
  const busImage = variant === "v1" ? busV1Side : busV2Side;

  return (
    <div className="relative" aria-label={`Bus ${number}`}>
      <img 
        src={busImage} 
        alt={`Bus ${number}`} 
        className="w-14 h-12 object-contain"
      />
      {/* Risk indicator dot */}
      <div 
        className="absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white" 
        style={{ backgroundColor: color }}
      />
    </div>
  );
}