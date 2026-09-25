import { useEffect } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { KpiBar } from "@/components/KpiBar/KpiBar";
import { BusMap } from "@/components/Map/BusMap";
import { SidePanel } from "@/components/Sidebar/SidePanel";
import { DrillDownPanel } from "@/components/DrillDown/DrillDownPanel";

export default function App() {
  const init = useDashboardStore(s => s.init);
  const selectedVehicleId = useDashboardStore(s => s.selectedVehicleId);
  const status = useDashboardStore(s => s.status);
  const refresh = useDashboardStore(s => s.refresh);
  useEffect(() => init(), [init]);

  return <div className="dashboard">
    <BusMap />
    <header className="topbar">
      <div className="brand"><span className="brand-mark">◉</span><span>Диспетчерская</span></div>
      <KpiBar />
      <div className="connection" title={status === "error" ? "Нет связи с API" : "Данные backend"}>
        <span className={`connection-dot ${status}`} />{status === "error" ? "Нет связи" : status === "loading" ? "Подключение" : "В сети"}
      </div>
    </header>
    <aside className="left-panel"><SidePanel /></aside>
    {selectedVehicleId && <aside className="right-panel"><DrillDownPanel /></aside>}
    {status === "error" && <div className="error-banner">Не удалось загрузить данные. <button onClick={() => void refresh()}>Повторить</button></div>}
  </div>;
}
