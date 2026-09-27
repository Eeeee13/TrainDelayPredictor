import type { LatLng } from "@/domain/types";

/**
 * Loads the shapes.geojson exported from the route shape editor
 * (route_shape_editor.html) — a FeatureCollection of LineStrings keyed by
 * `properties.route_id`. Adjust `url` if shapes end up served by the
 * backend instead of as a static asset.
 */
export async function loadRouteShapes(url = "/data/shapes.geojson"): Promise<Record<string, LatLng[]>> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to load route shapes: http ${res.status}`);
  const geojson = await res.json();

  const shapes: Record<string, LatLng[]> = {};
  for (const feature of geojson.features ?? []) {
    const routeId = String(feature.properties?.route_id ?? "");
    if (!routeId) continue;
    shapes[routeId] = (feature.geometry.coordinates as [number, number][]).map(([lng, lat]) => ({ lat, lng }));
  }
  return shapes;
}