import type { LatLng, Vehicle } from "@/domain/types";
import { snapToLine, SNAP_MAX_DISTANCE_M } from "./snapToRoute";
import { getShapeGeometry, distanceAlongShape, pointAtDistance, haversineMeters, type ShapeGeometry } from "./routeGeometry";

/** Fallback tween length when we have no prior update to measure the real interval from. */
const DEFAULT_DURATION_MS = 2000;
const MIN_DURATION_MS = 1000;

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
interface Sample {
  position: LatLng;
  timestamp: number;
  receivedAt: number;
  interval: number;
  shape: LatLng[] | undefined;
}
const samples = new Map<string, Sample>();

function unwrapDistance(geometry: ShapeGeometry, target: number, from: number): number {
  if (!geometry.isLoop || geometry.totalLength <= 0) return target;
  return target + Math.round((from - target) / geometry.totalLength) * geometry.totalLength;
}

export function resetVehicleAnimations(): void {
  anims.clear();
  samples.clear();
}

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

/** Only new per-vehicle measurements advance the animation clock.
 * Arrival intervals are measured in playback time, so accelerated CSV replay
 * works without treating historical GPS timestamps as wall-clock time.
 */
export function setVehicleTargets(vehicles: Vehicle[], shapeByVehicleId: Record<string, LatLng[]>, now: number): void {
  const seen = new Set<string>();
  for (const vehicle of vehicles) {
    seen.add(vehicle.id);
    const shape = shapeByVehicleId[vehicle.id];
    const previousSample = samples.get(vehicle.id);
    const timestamp = Date.parse(vehicle.lastUpdate);
    const samePosition = previousSample && previousSample.position.lat === vehicle.position.lat
      && previousSample.position.lng === vehicle.position.lng;
    const sameTimestamp = previousSample && (timestamp === previousSample.timestamp
      || (!Number.isFinite(timestamp) && !Number.isFinite(previousSample.timestamp)));
    if (previousSample && Number.isFinite(timestamp) && timestamp < previousSample.timestamp) continue;
    if (previousSample && sameTimestamp && samePosition && previousSample.shape === shape) continue;

    const fresh = !previousSample || !sameTimestamp || !samePosition;
    const interval = previousSample && fresh
      ? Math.max(MIN_DURATION_MS, now - previousSample.receivedAt)
      : previousSample?.interval ?? DEFAULT_DURATION_MS;
    // Smooth arrival jitter; never shorten a long GPS gap to a 400 ms sprint.
    const duration = previousSample ? Math.max(interval, previousSample.interval * 0.8) : interval;
    samples.set(vehicle.id, {
      position: { ...vehicle.position }, timestamp,
      receivedAt: fresh ? now : previousSample!.receivedAt,
      interval: duration, shape,
    });
    const prev = anims.get(vehicle.id);
    // Fresh timestamps with identical coordinates must not restart an in-flight tween.
    if (prev && samePosition && previousSample?.shape === shape) continue;

    const geometry = shape && shape.length >= 2 ? getShapeGeometry(shape) : null;
    const from = prev ? currentPositionOf(prev, now) : vehicle.position;
    const previousShape = prev?.mode === "shape" && prev.geometry === geometry ? prev : null;
    // A nearby GPS fix must not send the marker kilometres along another arm
    // of a crossing or an overlapping return leg. Prefer reachable segments.
    const routeBudget = previousSample
      ? Math.max(100, haversineMeters(previousSample.position, vehicle.position) * 3)
      : Infinity;
    const snap = geometry ? snapToLine(vehicle.position, geometry.points, candidate => {
      if (!previousShape) return true;
      const target = distanceAlongShape(geometry, candidate.segmentIndex, candidate.t);
      return Math.abs(unwrapDistance(geometry, target, previousShape.sTo) - previousShape.sTo) <= routeBudget;
    }) : null;

    if (geometry && snap && snap.distanceMeters <= SNAP_MAX_DISTANCE_M) {
      let sTo = distanceAlongShape(geometry, snap.segmentIndex, snap.t);
      let sFrom = sTo;
      if (previousShape) {
        sFrom = valueOf(previousShape, now);
        sTo = unwrapDistance(geometry, sTo, sFrom);
      } else if (prev) {
        const start = snapToLine(from, geometry.points);
        const startDistance = start ? distanceAlongShape(geometry, start.segmentIndex, start.t) : sTo;
        const targetDistance = unwrapDistance(geometry, sTo, startDistance);
        if (start && start.distanceMeters < 1 && Math.abs(targetDistance - startDistance) <= routeBudget) {
          sFrom = startDistance;
          sTo = targetDistance;
        } else {
          // Bridge the mode change without teleporting to the route.
          anims.set(vehicle.id, { mode: "raw", from, to: snap.point, tFrom: now, tTo: now + duration });
          continue;
        }
      }
      anims.set(vehicle.id, { mode: "shape", geometry, sFrom, sTo, tFrom: now, tTo: now + duration });
    } else {
      anims.set(vehicle.id, { mode: "raw", from, to: vehicle.position, tFrom: now, tTo: now + duration });
    }
  }

  for (const id of anims.keys()) if (!seen.has(id)) {
    anims.delete(id);
    samples.delete(id);
  }
}

export interface RenderedVehicle { position: LatLng; bearing: number | null }

/** Reads the current interpolated position (and, on a shape, the direction of travel) for one vehicle. */
export function getRenderedPosition(vehicleId: string, fallback: LatLng, now: number): RenderedVehicle {
  const anim = anims.get(vehicleId);
  if (!anim) return { position: fallback, bearing: null };
  if (anim.mode === "raw") return { position: valueOfRaw(anim, now), bearing: null };

  const s = valueOf(anim, now);
  const { point, bearing } = pointAtDistance(anim.geometry, s);
  return { position: point, bearing };
}
