import { useEffect, useRef } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import type { RiskLevel } from "@/domain/types";

/**
 * Fires a browser Notification the moment a vehicle *transitions into* HIGH
 * risk (not on every refresh while it stays high — tag dedupes that anyway,
 * but we also skip work for vehicles whose risk didn't change since last
 * check).
 */
export function useHighRiskNotifications() {
  const vehicles = useDashboardStore((s) => s.vehicles);
  const notificationsEnabled = useDashboardStore((s) => s.notificationsEnabled);
  const prevRisk = useRef<Record<string, RiskLevel | null>>({});

  useEffect(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return;
    if (!notificationsEnabled) return;
    if (Notification.permission === "granted") {
      for (const v of Object.values(vehicles)) {
        const was = prevRisk.current[v.id];
        if (v.risk === "high" && was !== "high") {
          const minutes = v.predictedDelaySeconds !== null ? Math.round(v.predictedDelaySeconds / 60) : null;
          new Notification(`Высокий риск — ${v.garageNumber}`, {
            body: minutes !== null ? `Прогнозируемое опоздание ~${minutes} мин` : "Прогноз формируется",
            tag: `risk-high-${v.id}`, // replaces any earlier notification for this same vehicle instead of stacking
            silent: false
          });
        }
      }
    }
    prevRisk.current = Object.fromEntries(Object.values(vehicles).map((v) => [v.id, v.risk]));
  }, [vehicles, notificationsEnabled]);
}

/** Current permission state, reactive so a toggle button can reflect it live. */
export function useNotificationPermission(): NotificationPermission | "unsupported" {
  const supported = typeof window !== "undefined" && typeof Notification !== "undefined";
  return supported ? Notification.permission : "unsupported";
}

const BellIcon = ({ muted = false }: { muted?: boolean }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    {muted && <line x1="5" y1="4" x2="19" y2="20" />}
  </svg>
);

export function NotificationToggle() {
  const permission = useNotificationPermission();
  const notificationsEnabled = useDashboardStore((s) => s.notificationsEnabled);
  const toggleNotifications = useDashboardStore((s) => s.toggleNotifications);

  if (permission === "unsupported") return null;

  if (permission === "granted") {
    return (
      <button
        onClick={toggleNotifications}
        className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-colors ${
          notificationsEnabled
            ? "text-gray-800 bg-gray-100 hover:bg-gray-200"
            : "text-gray-500 bg-gray-50 hover:bg-gray-100"
        }`}
      >
        <BellIcon muted={!notificationsEnabled} />
        {notificationsEnabled ? "Включены" : "Выключены"}
      </button>
    );
  }

  const denied = permission === "denied";
  return (
    <button
      onClick={() => { if (!denied) void Notification.requestPermission(); }}
      disabled={denied}
      title={denied ? "Уведомления заблокированы в настройках браузера" : undefined}
      className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
        denied ? "bg-gray-100 text-gray-400 cursor-not-allowed" : "bg-gray-100 text-gray-800 hover:bg-gray-200"
      }`}
    >
      <BellIcon muted={denied} />
      {denied ? "Заблокированы" : "Включить"}
    </button>
  );
}
