import { useDashboardStore } from "@/store/dashboardStore";
import { AlertEvent } from "@/domain/types";

const KIND_DOT: Record<AlertEvent["kind"], string> = {
  critical: "bg-risk-high",
  risk_increase: "bg-risk-mid",
  recovered: "bg-risk-low"
};

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function AlertsFeed() {
  const alerts = useDashboardStore((s) => s.alerts);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {alerts.length === 0 && (
          <div className="text-sm text-base-400 dark:text-base-400 text-gray-600 px-1 py-4">Событий пока нет</div>
        )}
        {alerts.map((a) => (
          <div key={a.id} className="flex items-start gap-2 text-xs px-1 py-1">
            <span className={`mt-1 h-1.5 w-1.5 rounded-full shrink-0 ${KIND_DOT[a.kind]}`} />
            <div className="min-w-0">
              <div className="text-base-300 dark:text-base-300 text-gray-700 leading-snug">{a.message}</div>
              <div className="text-base-400/70 dark:text-base-400/70 text-gray-500/70 text-[10px] mt-0.5">{formatTime(a.timestamp)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
