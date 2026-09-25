import { LatLng, RouteDef, RoutePoint, Stop } from "@/domain/types";

/**
 * Synthetic route network generator.
 *
 * This stands in for the "Ingestion Service + schedule reference tables"
 * described in the architecture doc — until the real NDTP schema and route
 * geometry arrive, the rest of the app (map, list, drill-down) is built
 * against this same shape, so swapping in real data later is a one-file
 * change (see services/liveFeed.ts).
 */

export const MAP_CENTER: LatLng = { lat: 56.9496, lng: 24.1052 }; // Riga city centre, used as a plausible demo network

const ROUTE_COLORS = [
  "#0a84ff",
  "#ff9f0a",
  "#bf5af2",
  "#64d2ff",
  "#ff375f",
  "#30d158"
];

function deg2rad(d: number) {
  return (d * Math.PI) / 180;
}

/** Offsets a lat/lng by meters (small-angle approximation, fine at city scale). */
function offset(base: LatLng, dNorthM: number, dEastM: number): LatLng {
  const R = 6378137;
  const dLat = (dNorthM / R) * (180 / Math.PI);
  const dLng =
    ((dEastM / (R * Math.cos(deg2rad(base.lat)))) * 180) / Math.PI;
  return { lat: base.lat + dLat, lng: base.lng + dLng };
}

/** Builds a wandering polyline of `segments` points around a center, then resamples with cumulative-distance `t`. */
function generateRoutePath(
  center: LatLng,
  seed: number,
  radiusM: number,
  segments: number
): RoutePoint[] {
  const raw: LatLng[] = [];
  let angle = seed * 37;
  let n = 0,
    e = 0;
  for (let i = 0; i < segments; i++) {
    angle += (Math.sin(i * 0.7 + seed) * 50 + (Math.random() - 0.5) * 30);
    const step = radiusM / segments;
    n += Math.cos(deg2rad(angle)) * step;
    e += Math.sin(deg2rad(angle)) * step;
    raw.push(offset(center, n, e));
  }

  // cumulative distance -> normalized t
  const dist = (a: LatLng, b: LatLng) =>
    Math.hypot(a.lat - b.lat, a.lng - b.lng);
  let total = 0;
  const cum: number[] = [0];
  for (let i = 1; i < raw.length; i++) {
    total += dist(raw[i - 1], raw[i]);
    cum.push(total);
  }
  return raw.map((p, i) => ({ ...p, t: total > 0 ? cum[i] / total : 0 }));
}

function makeStops(path: RoutePoint[], count: number, prefix: string): Stop[] {
  const stops: Stop[] = [];
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1);
    const idx = Math.min(
      path.length - 1,
      Math.round(t * (path.length - 1))
    );
    stops.push({
      id: `${prefix}-stop-${i}`,
      name: `Остановка ${i + 1}`,
      position: { lat: path[idx].lat, lng: path[idx].lng },
      sequence: i
    });
  }
  return stops;
}

export function generateRoutes(count: number): RouteDef[] {
  const routes: RouteDef[] = [];
  for (let i = 0; i < count; i++) {
    const id = `R${i + 1}`;
    const path = generateRoutePath(MAP_CENTER, i, 2600 + (i % 3) * 500, 60);
    const stopCount = 7 + (i % 4);
    routes.push({
      id,
      shortName: String(i + 1),
      longName: `Маршрут ${i + 1}`,
      color: ROUTE_COLORS[i % ROUTE_COLORS.length],
      path,
      stops: makeStops(path, stopCount, id)
    });
  }
  return routes;
}

/** Interpolates a position + heading (deg) for a fractional progress along a route path. */
export function samplePathAt(
  path: RoutePoint[],
  progress: number
): { position: LatLng; heading: number } {
  const p = Math.max(0, Math.min(1, progress));
  let i = 0;
  while (i < path.length - 2 && path[i + 1].t < p) i++;
  const a = path[i];
  const b = path[Math.min(i + 1, path.length - 1)];
  const span = Math.max(1e-6, b.t - a.t);
  const localT = Math.max(0, Math.min(1, (p - a.t) / span));
  const lat = a.lat + (b.lat - a.lat) * localT;
  const lng = a.lng + (b.lng - a.lng) * localT;
  const dLat = b.lat - a.lat;
  const dLng = (b.lng - a.lng) * Math.cos(deg2rad(a.lat));
  const heading = (Math.atan2(dLng, dLat) * 180) / Math.PI;
  return { position: { lat, lng }, heading: (heading + 360) % 360 };
}
