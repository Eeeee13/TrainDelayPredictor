import { useDashboardStore } from "@/store/dashboardStore";
import type { RiskLevel } from "@/domain/types";
const levels: {value:RiskLevel;label:string}[] = [
  {value:"low",label:"Низкий"},{value:"medium",label:"Средний"},{value:"high",label:"Высокий"}
];
export function FilterBar() {
  const filters = useDashboardStore(s => s.filters);
  const setFilters = useDashboardStore(s => s.setFilters);
  const routes = useDashboardStore(s => s.routes);
  const toggle = (level: RiskLevel) => {
    const active = filters.riskLevels ?? [];
    const next = active.includes(level) ? active.filter(x => x !== level) : [...active, level];
    setFilters({riskLevels: next.length ? next : null});
  };
  return <div className="filters">
    <input aria-label="Поиск борта или маршрута" value={filters.query} onChange={e => setFilters({query:e.target.value})} placeholder="Поиск борта или маршрута" />
    <div className="filter-row">
      <select aria-label="Маршрут" value={filters.routeIds?.[0] ?? ""} onChange={e => setFilters({routeIds:e.target.value ? [e.target.value] : null})}>
        <option value="">Все маршруты</option>
        {routes.map(r => <option key={r.vehicleId} value={r.id}>{r.shortName}</option>)}
      </select>
      <label className="predicted-toggle"><input type="checkbox" checked={filters.onlyPredicted} onChange={e => setFilters({onlyPredicted:e.target.checked})} /> С прогнозом</label>
    </div>
    <div className="risk-filters">
      {levels.map(level => <button key={level.value} className={`risk-filter ${filters.riskLevels?.includes(level.value) ? "active" : ""}`} onClick={() => toggle(level.value)}><span className={`risk-dot ${level.value}`} />{level.label}</button>)}
    </div>
  </div>;
}
