import type { LatLng, RouteDef, Vehicle } from "@/domain/types";

/**
 * Resolves each vehicle's road-shaped polyline.
 *
 * Shapes are keyed by the human-readable route number, the same key the
 * shape editor exports (`route_id` in shapes.geojson). We look it up via
 * `RouteDef.shortName` first, `RouteDef.id` as a fallback, and finally
 * `Vehicle.routeId` directly for any vehicle with no matching `RouteDef`
 * in the current snapshot.
 */
export function buildShapeByVehicleId(
  routes: RouteDef[],
  vehicles: Record<string, Vehicle>,
  routeShapes: Record<string, LatLng[]>
): Record<string, LatLng[]> {
  const shapeByVehicleId: Record<string, LatLng[]> = {};

  for (const route of routes) {
    const shape = routeShapes[route.shortName] ?? routeShapes[route.id];
    if (shape) shapeByVehicleId[route.vehicleId] = shape;
  }

  for (const vehicle of Object.values(vehicles)) {
    if (!shapeByVehicleId[vehicle.id] && routeShapes[vehicle.routeId]) {
      shapeByVehicleId[vehicle.id] = routeShapes[vehicle.routeId];
    }
  }

  return shapeByVehicleId;
}