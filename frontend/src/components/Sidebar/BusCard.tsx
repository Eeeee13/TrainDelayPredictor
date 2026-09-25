import type { RouteDef,Vehicle } from "@/domain/types";
import { BusSideIcon } from "./BusSideIcon";
export function BusCard({vehicle,route,selected,onSelect}:{vehicle:Vehicle;route?:RouteDef;selected:boolean;onSelect:()=>void}){
  const risk=vehicle.risk??"unknown";
  return <button className={`bus-card ${selected?"selected":""}`} onClick={onSelect}>
    <BusSideIcon risk={risk} number={route?.shortName??vehicle.garageNumber}/>
    <div className="bus-info"><strong>Борт {vehicle.garageNumber}</strong><small>{vehicle.risk===null?"Ожидает прогноза":vehicle.risk==="low"?"по графику":vehicle.risk==="medium"?"небольшое отставание":"риск опоздания"}</small></div>
    <div className={`bus-delay ${risk}`}>{vehicle.predictedDelaySeconds===null?"—":`${vehicle.predictedDelaySeconds > 0 ? "+" : ""}${Math.round(vehicle.predictedDelaySeconds/60)} мин`}</div>
  </button>;
}
