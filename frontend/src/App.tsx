import { useEffect } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { KpiBar } from "@/components/KpiBar/KpiBar";
import { BusMap } from "@/components/Map/BusMap";
import { SidePanel } from "@/components/Sidebar/SidePanel";
import { DrillDownPanel } from "@/components/DrillDown/DrillDownPanel";

export default function App() {
  const init = useDashboardStore((s) => s.init);
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);

  useEffect(() => {
    const unsubscribe = init();
    return unsubscribe;
  }, [init]);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-base-50">
      {/* Map fills the entire viewport — every other element floats above it. */}
      <BusMap />

      {/* Top status + KPI bar */}
      <div className="pointer-events-none absolute top-4 left-4 right-4 z-30 flex justify-center">
        <div className="pointer-events-auto flex items-center gap-4 rounded-full bg-white/90 backdrop-blur-xl border border-gray-200 shadow-panel px-4 py-2.5">
          <div className="flex items-center gap-2 pr-1 border-r border-gray-300">
            <span className="h-1.5 w-1.5 rounded-full bg-risk-low animate-pulse" />
            <span className="text-[13px] font-semibold text-gray-800">Диспетчерская</span>
          </div>
          <KpiBar />
        </div>
      </div>

      {/* Left floating panel: bus list / alerts */}
      <div className="pointer-events-none absolute left-4 top-[76px] bottom-4 z-20 w-[300px]">
        <SidePanel />
      </div>

      {/* Right floating panel: drill-down, only while a vehicle is selected */}
      {selectedVehicleId && (
        <div className="pointer-events-none absolute right-4 top-[76px] bottom-24 z-20">
          <DrillDownPanel />
        </div>
      )}
    </div>
  );
}
