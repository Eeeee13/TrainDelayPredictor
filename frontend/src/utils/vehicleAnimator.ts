import type { LatLng, Vehicle } from "@/domain/types";
import { snapToLine, SNAP_MAX_DISTANCE_M } from "./snapToRoute";
import { getShapeGeometry, distanceAlongShape, pointAtDistance, type ShapeGeometry } from "./routeGeometry";

/** Fallback tween length when we have no prior update to measure the real interval from. */
const DEFAULT_DURATION_MS = 2000;
const MIN_DURATION_MS = 400;
const MAX_DURATION_MS = 4000;

interface ShapeAnim { mode: "shape"; geometry: ShapeGeometry; sFrom: number; sTo: number; tFrom: number; tTo: number }
interface RawAnim { mode: "raw"; from: LatLng; to: LatLng; tFrom: number; tTo: number }
type VehicleAnim = ShapeAnim | RawAnim;

/**
 * Per-vehicle animation targets, module-level rather than React state on
 * purpose: they're read every animation frame, and re-rendering the React
 * tree 60 times a second just to move a marker would be wasteful — the map
 * source is updated imperatively instead (see BusMap's rAF loop).
 */
const anims = new Map<string, VehicleAnim>();
let lastBatchAt: number | null = null;

function progress(tFrom: number, tTo: number, now: number): number {
  const span = tTo - tFrom;
  return span <= 0 ? 1 : Math.min(1, Math.max(0, (now - tFrom) / span));
}

function valueOf(anim: ShapeAnim, now: number): number {
  return anim.sFrom + (anim.sTo - anim.sFrom) * progress(anim.tFrom, anim.tTo, now);
}

function valueOfRaw(anim: RawAnim, now: number): LatLng {
  const t = progress(anim.tFrom, anim.tTo, now);
  return { lat: anim.from.lat + (anim.to.lat - anim.from.lat) * t, lng: anim.from.lng + (anim.to.lng - anim.from.lng) * t };
}

function currentPositionOf(anim: VehicleAnim, now: number): LatLng {
  return anim.mode === "raw" ? valueOfRaw(anim, now) : pointAtDistance(anim.geometry, valueOf(anim, now)).point;
}

/**
 * Registers a fresh snapshot from the store as the new animation target for
 * each vehicle. The tween always starts from wherever the vehicle is
 * *currently rendered* (not from the previous target), so a snapshot that
 * arrives mid-animation never causes a visible jump.
 *
 * Tween duration adapts to however long the actual gap since the last
 * snapshot was, so motion stays smooth whether updates land every 2s on the
 * polling timer or sooner via a websocket push.
 */
export function setVehicleTargets(vehicles: Vehicle[], shapeByVehicleId: Record<string, LatLng[]>, now: number): void {
  const duration = lastBatchAt ? Math.min(MAX_DURATION_MS, Math.max(MIN_DURATION_MS, now - lastBatchAt)) : DEFAULT_DURATION_MS;
  lastBatchAt = now;

  const seen = new Set<string>();
  for (const vehicle of vehicles) {
    seen.add(vehicle.id);
    const shape = shapeByVehicleId[vehicle.id];
    const snap = shape ? snapToLine(vehicle.position, shape) : null;
    const prev = anims.get(vehicle.id);

    if (snap && snap.distanceMeters <= SNAP_MAX_DISTANCE_M) {
      const geometry = getShapeGeometry(shape!);
      let sTo = distanceAlongShape(geometry, snap.segmentIndex, snap.t);

      let sFrom: number;
      if (prev) {
        sFrom = prev.mode === "shape" && prev.geometry === geometry
          ? valueOf(prev, now)
          : distanceAlongShape(geometry, snap.segmentIndex, snap.t); // switched shape/mode — reappear here, don't backtrack from an unrelated point
        // On a closed loop, prefer wrapping around the seam over snapping backward across the whole route.
        if (geometry.isLoop && geometry.totalLength > 0) {
          const direct = sTo - sFrom;
          const wrapped = direct - Math.sign(direct || 1) * geometry.totalLength;
          if (Math.abs(wrapped) < Math.abs(direct)) sTo = sFrom + wrapped;
        }
      } else {
        sFrom = sTo; // first sighting — appear exactly where it is, no tween
      }

      anims.set(vehicle.id, { mode: "shape", geometry, sFrom, sTo, tFrom: now, tTo: now + duration });
    } else {
      const from = prev ? currentPositionOf(prev, now) : vehicle.position;
      anims.set(vehicle.id, { mode: "raw", from, to: vehicle.position, tFrom: now, tTo: now + duration });
    }
  }

  for (const id of anims.keys()) if (!seen.has(id)) anims.delete(id);
}

export interface RenderedVehicle { position: LatLng; bearing: number | null }

/** Reads the current interpolated position (and, on a shape, the direction of travel) for one vehicle. */
export function getRenderedPosition(vehicleId: string, fallback: LatLng, now: number): RenderedVehicle {
  const anim = anims.get(vehicleId);
  if (!anim) return { position: fallback, bearing: null };
  if (anim.mode === "raw") return { position: valueOfRaw(anim, now), bearing: null };

  const total = anim.geometry.totalLength;
  const s = total > 0 ? ((valueOf(anim, now) % total) + total) % total : 0;
  const { point, bearing } = pointAtDistance(anim.geometry, s);
  return { position: point, bearing };
}