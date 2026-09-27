import type { RiskAssessment, RouteDef, Vehicle } from "@/domain/types";

interface ApiStop { id: string; sequence: number; scheduled_time: string; position: {lat:number;lng:number} }
interface ApiRoute { id: string; vehicle_id: string; short_name: string; stops: ApiStop[] }
interface ApiVehicle {
  vehicle_id: string; tr_id: number; position: {lat:number;lng:number}; speed_kmh: number;
  event_time: string; cur_dev_s: number | null; risk: RiskAssessment | null;
  trail: {lat:number;lng:number}[];
}
interface Snapshot { vehicles: ApiVehicle[]; routes: ApiRoute[] }
const base = import.meta.env.VITE_API_BASE_URL ?? "";

function utc(value: string): string { return /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`; }

export async function fetchDashboard(): Promise<{vehicles: Vehicle[]; routes: RouteDef[]}> {
  const response = await fetch(`${base}/dashboard/snapshot`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data: Snapshot = await response.json();
  return {
    routes: data.routes.map((route) => ({
      id: route.id, vehicleId: route.vehicle_id, shortName: route.short_name,
      stops: route.stops.map((stop) => ({id: stop.id, sequence: stop.sequence,
        scheduledTime: utc(stop.scheduled_time), position: stop.position}))
    })),
    vehicles: data.vehicles.map((v) => ({
      id: v.vehicle_id, routeId: String(v.tr_id), garageNumber: String(v.tr_id),
      position: v.position, trail: v.trail ?? [], speedKmh: v.speed_kmh, lastUpdate: utc(v.event_time),
      delaySeconds: v.cur_dev_s, predictedDelaySeconds: v.risk?.predicted_delay_s ?? null,
      risk: v.risk?.risk_level ?? null, targetStopId: v.risk ? String(v.risk.target_stop_id) : null,
      targetTime: v.risk ? utc(v.risk.target_time_begin) : null, source: v.risk?.source ?? null,
      reason: v.risk?.reason ?? null
    }))
  };
}

export function subscribeRisks(onUpdate: () => void): () => void {
  let closed = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  const connect = () => {
    const url = new URL(`${base}/ws/risk`, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(url);
    socket.onmessage = () => onUpdate();
    socket.onclose = () => { if (!closed) retry = setTimeout(connect, 3000); };
    socket.onerror = () => socket?.close();
  };
  connect();
  return () => { closed = true; if (retry) clearTimeout(retry); socket?.close(); };
}