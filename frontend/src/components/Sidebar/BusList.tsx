import { useMemo } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusCard } from "./BusCard";
export function BusList(){
  const vehicles=useDashboardStore(s=>s.vehicles);
  const routes=useDashboardStore(s=>s.routes);
  const filters=useDashboardStore(s=>s.filters);
  const selected=useDashboardStore(s=>s.selectedVehicleId);
  const select=useDashboardStore(s=>s.selectVehicle);
  const list=useMemo(()=>Object.values(vehicles).filter(v=>{
    if(filters.routeIds&&!filters.routeIds.includes(v.routeId))return false;
    if(filters.riskLevels&&(!v.risk||!filters.riskLevels.includes(v.risk)))return false;
    if(filters.onlyPredicted&&v.predictedDelaySeconds===null)return false;
    const q=filters.query.trim().toLowerCase();
    return !q||`${v.id} ${v.garageNumber} ${v.routeId}`.toLowerCase().includes(q);
  }).sort((a,b)=>(b.predictedDelaySeconds??-Infinity)-(a.predictedDelaySeconds??-Infinity)),[vehicles,filters]);
  return <div className="bus-list">{list.length?list.map(v=><BusCard key={v.id} vehicle={v} route={routes.find(r=>r.vehicleId===v.id)} selected={v.id===selected} onSelect={()=>select(v.id===selected?null:v.id)}/>):<div className="empty-state">Транспорт по выбранным фильтрам не найден</div>}</div>;
}
