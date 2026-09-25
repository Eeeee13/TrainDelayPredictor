import { useDashboardStore } from "@/store/dashboardStore";
export function DrillDownPanel(){
  const id=useDashboardStore(s=>s.selectedVehicleId);
  const vehicle=useDashboardStore(s=>id?s.vehicles[id]:undefined);
  const route=useDashboardStore(s=>s.routes.find(r=>r.vehicleId===id));
  const select=useDashboardStore(s=>s.selectVehicle);
  if(!vehicle)return null;
  const target=route?.stops.find(s=>s.id===vehicle.targetStopId);
  return <div className="panel detail-panel">
    <div className="detail-head"><div><small>ТРАНСПОРТНОЕ СРЕДСТВО</small><h2>Борт {vehicle.garageNumber}</h2><p>Маршрут {route?.shortName??vehicle.routeId}</p></div><button aria-label="Закрыть" onClick={()=>select(null)}>×</button></div>
    <div className="detail-grid"><div><small>Текущее отклонение</small><strong>{vehicle.delaySeconds===null?"—":`${Math.round(vehicle.delaySeconds/60)} мин`}</strong></div><div><small>Прогноз 10–15 мин</small><strong className={vehicle.risk??""}>{vehicle.predictedDelaySeconds===null?"—":`${vehicle.predictedDelaySeconds > 0 ? "+" : ""}${Math.round(vehicle.predictedDelaySeconds/60)} мин`}</strong></div></div>
    <div className="detail-section"><small>ПРОБЛЕМНЫЙ УЧАСТОК</small><p>{target?`До остановки №${target.sequence}`:"Целевая остановка пока не определена"}</p><p className="muted">{vehicle.targetTime?`Плановое прибытие: ${new Date(vehicle.targetTime).toLocaleString("ru-RU")}`:"Прогноз появится при входе в горизонт 10–15 минут"}</p></div>
    <div className="detail-section"><small>ПОСЛЕДНЯЯ ТЕЛЕМЕТРИЯ</small><p>{new Date(vehicle.lastUpdate).toLocaleString("ru-RU")}</p><p className="muted">Скорость {Math.round(vehicle.speedKmh)} км/ч · Источник {vehicle.source??"GPS"}</p></div>
    <div className="detail-section stops"><small>БЛИЖАЙШИЕ ОСТАНОВКИ</small>{route?.stops.map(stop=><div className={stop.id===vehicle.targetStopId?"target":""} key={stop.id}><span>№{stop.sequence}</span><time>{new Date(stop.scheduledTime).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}</time></div>)}</div>
  </div>;
}
