import type { LatLng } from "@/domain/types";

/**
 * Beyond this distance from the shape we trust the raw GPS fix instead —
 * likely a depot, a detour, or a route the shape doesn't cover yet.
 */
export const SNAP_MAX_DISTANCE_M = 60;

const EARTH_RADIUS_M = 6371000;

function toLocalXY(point: LatLng, originLat: number): [number, number] {
  const originLatRad = (originLat * Math.PI) / 180;
  return [
    ((point.lng * Math.PI) / 180) * EARTH_RADIUS_M * Math.cos(originLatRad),
    (point.lat * Math.PI) / 180 * EARTH_RADIUS_M,
  ];
}

export interface SnapResult {
  point: LatLng;
  distanceMeters: number;
  segmentIndex: number;
  /** 0..1 — fraction along the segment; handy later for progress-along-route. */
  t: number;
}

/**
 * Projects `pos` onto the closest point of any *segment* of `line` — not
 * onto the closest vertex. Shape waypoints are placed by hand in the route
 * editor and can be sparse, so vertex-snapping would cut corners badly.
 *
 * Distances are computed in a local equirectangular projection (metres)
 * rather than raw degrees, so results stay correct across a whole city
 * despite longitude degrees shrinking with latitude.
 */
export function snapToLine(pos: LatLng, line: LatLng[], accept: (candidate: SnapResult) => boolean = () => true): SnapResult | null {
  if (line.length < 2) return null;

  const p = toLocalXY(pos, pos.lat);
  let best: SnapResult | null = null;

  for (let i = 0; i < line.length - 1; i++) {
    const a = toLocalXY(line[i], pos.lat);
    const b = toLocalXY(line[i + 1], pos.lat);
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const lenSq = abx * abx + aby * aby;

    let t = lenSq === 0 ? 0 : ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / lenSq;
    t = Math.min(1, Math.max(0, t));

    const dx = p[0] - (a[0] + t * abx);
    const dy = p[1] - (a[1] + t * aby);
    const distanceMeters = Math.hypot(dx, dy);

    if (!best || distanceMeters < best.distanceMeters) {
      const candidate: SnapResult = {
        point: {
          lat: line[i].lat + t * (line[i + 1].lat - line[i].lat),
          lng: line[i].lng + t * (line[i + 1].lng - line[i].lng),
        },
        distanceMeters,
        segmentIndex: i,
        t,
      };
      if (accept(candidate)) best = candidate;
    }
  }

  return best;
}

/**
 * Snaps `pos` onto `line` for display, but only when it's close enough to
 * trust the shape. Falls back to the raw point otherwise (no shape, or the
 * vehicle is genuinely off-route).
 */
export function snapPositionForDisplay(pos: LatLng, line: LatLng[] | undefined): LatLng {
  if (!line) return pos;
  const snap = snapToLine(pos, line);
  return snap && snap.distanceMeters <= SNAP_MAX_DISTANCE_M ? snap.point : pos;
}