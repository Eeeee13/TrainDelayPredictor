import { useEffect, useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";

function Pill({ value, label, tone }: { value: string; label: string; tone?: "risk" }) {
  return (
    <div className="flex items-baseline gap-1.5 px-3 first:pl-0 last:pr-0">
      <span className={`text-[15px] font-semibold tabular-nums ${tone === "risk" ? "text-risk-mid" : "text-gray-800"}`}>
        {value}
      </span>
      <span className="text-[11px] text-gray-600">{label}</span>
    </div>
  );
}

export function KpiBar() {
  const kpi = useDashboardStore((s) => s.kpi);
  const predictedCount = Object.values(useDashboardStore((s) => s.vehicles)).filter(v => v.predictedDelaySeconds !== null).length;
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await fetch("/simulation", { cache: "no-store" });
        if (!response.ok || cancelled) return;
        const data = await response.json();
        setRunning(Boolean(data.replay || data.emulator));
      } catch {
        if (!cancelled) setRunning(false);
      }
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  async function act(path: "start" | "stop") {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/simulation/${path}`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(typeof data.detail === "string" ? data.detail : "не удалось");
        return;
      }
      setRunning(Boolean(data.replay || data.emulator));
      if (Array.isArray(data.errors) && data.errors.length) setError(data.errors.join("; "));
    } catch {
      setError("нет связи с сервером");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center divide-x divide-gray-300">
      <Pill value={predictedCount ? `${kpi.onTimePct}%` : "—"} label="по графику" />
      <Pill value={predictedCount ? `${kpi.atRiskPct}%` : "—"} label="в риске" tone="risk" />
      <Pill value={predictedCount ? `${Math.round(kpi.avgPredictedDelaySec / 60)} мин` : "—"} label="ср. отклонение" />
      <div className="flex items-center gap-1.5 pl-3">
        <button
          type="button"
          title="Запуск проигрывания с 6:00 и эмулятора"
          disabled={busy}
          onClick={() => act("start")}
          className="rounded-full bg-gray-900 px-3 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
        >
          Старт
        </button>
        <button
          type="button"
          title="Остановить проигрывание и эмулятор"
          disabled={busy}
          onClick={() => act("stop")}
          className="rounded-full border border-gray-300 px-3 py-1 text-[11px] font-semibold text-gray-800 disabled:opacity-50"
        >
          Стоп
        </button>
        <span className={`text-[11px] ${error ? "text-risk-mid" : "text-gray-500"}`} title={error ?? undefined}>
          {error ? "ошибка" : running ? "идёт" : "стоп"}
        </span>
      </div>
    </div>
  );
}
