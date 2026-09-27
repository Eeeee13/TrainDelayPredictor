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
  const color = RISK_COLOR[risk]; // was used before for colored icon gen
  const variant = getBusVariant(vehicleId);
  const busImage = variant === "v1" ? busV1Side : busV2Side;

  return (
    <div className="relative overflow-hidden" aria-label={`Bus ${number}`}>
      <img 
        src={busImage} 
        alt={`Bus ${number}`} 
        className="w-[4.55rem] h-[3.9rem] object-contain translate-x-4 pointer-events-none"
        style={{ transform: 'scaleX(1) translateX(-1.5rem) scale(1.5)' }}
      />
    </div>
  );
}