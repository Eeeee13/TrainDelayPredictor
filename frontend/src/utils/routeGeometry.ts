import type { LatLng } from "@/domain/types";

const EARTH_RADIUS_M = 6371000;
/** First and last shape point closer than this are treated as a closed loop. */
const LOOP_CLOSURE_THRESHOLD_M = 30;

export function haversineMeters(a: LatLng, b: LatLng): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(s));
}

export interface ShapeGeometry {
  points: LatLng[];
  /** cumulative[i] = distance in meters from points[0] to points[i]. */
  cumulative: number[];
  totalLength: number;
  /** True when the shape's start and end are the same physical point (a circular route). */
  isLoop: boolean;
}

// Shapes are loaded once and kept as stable array references for the whole
// session, so caching by reference (no manual invalidation needed) is safe.
const geometryCache = new WeakMap<LatLng[], ShapeGeometry>();

export function getShapeGeometry(shape: LatLng[]): ShapeGeometry {
  const cached = geometryCache.get(shape);
  if (cached) return cached;

  const cumulative = [0];
  for (let i = 1; i < shape.length; i++) {
    cumulative.push(cumulative[i - 1] + haversineMeters(shape[i - 1], shape[i]));
  }
  const totalLength = cumulative[cumulative.length - 1] ?? 0;
  const isLoop = shape.length > 2 && haversineMeters(shape[0], shape[shape.length - 1]) <= LOOP_CLOSURE_THRESHOLD_M;

  const geometry: ShapeGeometry = { points: shape, cumulative, totalLength, isLoop };
  geometryCache.set(shape, geometry);
  return geometry;
}

/** Arc-length distance from the shape's start to a point given as (segmentIndex, t) — see `snapToLine`. */
export function distanceAlongShape(geometry: ShapeGeometry, segmentIndex: number, t: number): number {
  const segLen = geometry.cumulative[segmentIndex + 1] - geometry.cumulative[segmentIndex];
  return geometry.cumulative[segmentIndex] + t * segLen;
}

/** Inverse of the above: the point and direction of travel at a given arc-length distance. */
export function pointAtDistance(geometry: ShapeGeometry, distanceMeters: number): { point: LatLng; bearing: number } {
  const { points, cumulative, totalLength } = geometry;
  const d = geometry.isLoop && totalLength > 0
    ? ((distanceMeters % totalLength) + totalLength) % totalLength
    : Math.min(Math.max(distanceMeters, 0), totalLength);

  let i = 1;
  while (i < cumulative.length - 1 && cumulative[i] < d) i++;
  const segStart = cumulative[i - 1];
  const segLen = cumulative[i] - segStart || 1;
  const t = (d - segStart) / segLen;

  const a = points[i - 1];
  const b = points[i];
  return {
    point: { lat: a.lat + t * (b.lat - a.lat), lng: a.lng + t * (b.lng - a.lng) },
    bearing: (Math.atan2(b.lng - a.lng, b.lat - a.lat) * 180 / Math.PI + 360) % 360,
  };
}