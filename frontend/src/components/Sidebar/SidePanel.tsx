import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusList } from "./BusList";
import { FilterBar } from "@/components/Filters/FilterBar";
export function SidePanel(){
  const [tab,setTab]=useState<"buses"|"alerts">("buses");
  const vehicles=useDashboardStore(s=>s.vehicles);
  const alerts=Object.values(vehicles).filter(v=>v.risk==="high"||v.risk==="medium");
  return <div className="panel side-panel">
    <div className="tabs"><button className={tab==="buses"?"active":""} onClick={()=>setTab("buses")}>ТС</button><button className={tab==="alerts"?"active":""} onClick={()=>setTab("alerts")}>Алерты {alerts.length||""}</button></div>
    {tab==="buses" ? <><FilterBar/><BusList/></> : <div className="bus-list">{alerts.length ? alerts.map(v=><div className="alert-card" key={v.id}><span className={`risk-dot ${v.risk}`}/><div><strong>Борт {v.garageNumber}</strong><p>Прогноз опоздания +{Math.round((v.predictedDelaySeconds??0)/60)} мин</p></div></div>) : <div className="empty-state">Активных алертов нет</div>}</div>}
    <div className="legend"><span><i className="risk-dot low"/>низкий</span><span><i className="risk-dot medium"/>средний</span><span><i className="risk-dot high"/>высокий</span></div>
  </div>;
}
