import {
  AlertEvent,
  RouteDef,
  ScheduleSample,
  Vehicle,
  riskFromDelaySeconds
} from "@/domain/types";
import { generateRoutes, samplePathAt } from "./network";

/**
 * Mock replacement for the real "WebSocket-хаб" / Risk Aggregator push
 * channel described in section 7-8 of the architecture doc. It exposes the
 * exact shape the real backend would (a subscribe() returning vehicles +
 * alerts), so the UI layer never needs to know it's talking to a
 * `setInterval` instead of a socket. Swap this module for a real
 * `WebSocket("wss://.../dispatch")` client without touching components.
 */

const DEPOTS = ["Парк №1", "Парк №2", "Парк №3"];

export interface LiveSnapshot {
  vehicles: Vehicle[];
  newAlerts: AlertEvent[];
}

type Listener = (snapshot: LiveSnapshot) => void;

const TICK_MS = 1200;
const VEHICLES_PER_ROUTE = 3;

function buildInitialSchedule(baseDelay: number): ScheduleSample[] {
  const samples: ScheduleSample[] = [];
  let drift = baseDelay / 60;
  for (let i = 0; i < 24; i++) {
    drift += (Math.random() - 0.45) * 0.4;
    samples.push({
      t: i * 5,
      planned: i * 5,
      actual: i * 5 + drift
    });
  }
  return samples;
}

export class LiveFeedService {
  readonly routes: RouteDef[];
  private vehicles: Map<string, Vehicle> = new Map();
  private listeners = new Set<Listener>();
  private timer: number | null = null;

  constructor(routeCount = 9) {
    this.routes = generateRoutes(routeCount);
    this.seedVehicles();
  }

  private seedVehicles() {
    for (const route of this.routes) {
      for (let v = 0; v < VEHICLES_PER_ROUTE; v++) {
        const id = `${route.id}-V${v + 1}`;
        const progress = Math.random();
        const { position, heading } = samplePathAt(route.path, progress);
        const baseDelaySec = Math.random() < 0.7 ? Math.random() * 90 : 90 + Math.random() * 420;
        this.vehicles.set(id, {
          id,
          routeId: route.id,
          garageNumber: `${1000 + Math.floor(Math.random() * 8000)}`,
          position,
          heading,
          speedKmh: 18 + Math.random() * 22,
          progress,
          delaySeconds: baseDelaySec,
          predictedDelaySeconds: baseDelaySec * (0.85 + Math.random() * 0.4),
          predictedHorizonMinutes: 12,
          risk: riskFromDelaySeconds(baseDelaySec),
          lastUpdate: Date.now(),
          depot: DEPOTS[v % DEPOTS.length],
          schedule: buildInitialSchedule(baseDelaySec)
        });
      }
    }
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    if (!this.timer) {
      this.timer = window.setInterval(() => this.tick(), TICK_MS);
    }
    // deliver an immediate snapshot so new subscribers don't wait a full tick
    listener({ vehicles: Array.from(this.vehicles.values()), newAlerts: [] });
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer) {
        window.clearInterval(this.timer);
        this.timer = null;
      }
    };
  }

  private tick() {
    const newAlerts: AlertEvent[] = [];
    const routeById = new Map(this.routes.map((r) => [r.id, r]));

    for (const vehicle of this.vehicles.values()) {
      const route = routeById.get(vehicle.routeId)!;
      const speedFraction = (vehicle.speedKmh / 3.6) * (TICK_MS / 1000) / 5200; // rough normalization vs route length
      let progress = vehicle.progress + speedFraction;
      if (progress >= 1) progress -= 1;
      const { position, heading } = samplePathAt(route.path, progress);

      const prevRisk = vehicle.risk;
      const delayDrift = (Math.random() - 0.48) * 18;
      const delaySeconds = Math.max(0, vehicle.delaySeconds + delayDrift);
      const predictedDelaySeconds = Math.max(
        0,
        delaySeconds * (0.9 + Math.random() * 0.25)
      );
      const risk = riskFromDelaySeconds(predictedDelaySeconds);

      vehicle.progress = progress;
      vehicle.position = position;
      vehicle.heading = heading;
      vehicle.speedKmh = Math.max(5, vehicle.speedKmh + (Math.random() - 0.5) * 3);
      vehicle.delaySeconds = delaySeconds;
      vehicle.predictedDelaySeconds = predictedDelaySeconds;
      vehicle.risk = risk;
      vehicle.lastUpdate = Date.now();
      vehicle.schedule = [
        ...vehicle.schedule.slice(1),
        {
          t: vehicle.schedule[vehicle.schedule.length - 1].t + 5,
          planned: vehicle.schedule[vehicle.schedule.length - 1].planned + 5,
          actual:
            vehicle.schedule[vehicle.schedule.length - 1].planned +
            5 +
            predictedDelaySeconds / 60
        }
      ];

      if (prevRisk !== "high" && risk === "high") {
        newAlerts.push({
          id: `${vehicle.id}-${vehicle.lastUpdate}`,
          vehicleId: vehicle.id,
          routeShortName: route.shortName,
          kind: "critical",
          message: `Автобус ${vehicle.garageNumber} (маршрут ${route.shortName}): риск опоздания вырос до критического`,
          timestamp: vehicle.lastUpdate
        });
      } else if (prevRisk === "high" && risk !== "high") {
        newAlerts.push({
          id: `${vehicle.id}-${vehicle.lastUpdate}`,
          vehicleId: vehicle.id,
          routeShortName: route.shortName,
          kind: "recovered",
          message: `Автобус ${vehicle.garageNumber} (маршрут ${route.shortName}): график восстановлен`,
          timestamp: vehicle.lastUpdate
        });
      } else if (prevRisk === "low" && risk === "mid") {
        newAlerts.push({
          id: `${vehicle.id}-${vehicle.lastUpdate}`,
          vehicleId: vehicle.id,
          routeShortName: route.shortName,
          kind: "risk_increase",
          message: `Автобус ${vehicle.garageNumber} (маршрут ${route.shortName}): начал отставать от графика`,
          timestamp: vehicle.lastUpdate
        });
      }
    }

    const snapshot: LiveSnapshot = {
      vehicles: Array.from(this.vehicles.values()),
      newAlerts
    };
    for (const listener of this.listeners) listener(snapshot);
  }
}

export const liveFeed = new LiveFeedService();
