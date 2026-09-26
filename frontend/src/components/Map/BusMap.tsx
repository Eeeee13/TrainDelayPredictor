import { useEffect, useMemo, useRef, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
maplibregl.setWorkerUrl(workerUrl);
import { useDashboardStore } from "@/store/dashboardStore";
import type { RouteDef, RiskLevel, Vehicle } from "@/domain/types";
import { getBusVariant, BusVariant } from "@/utils/busVariant";
import { BusTopIcon } from "./BusTopIcon";

/** Base pixel width the map's raster bus icons are rendered at; @2x for crisp retina rendering. */
const MAP_ICON_BASE_SIZE = 40;

const LABEL_ZOOM_THRESHOLD = 13;
const ICON_ZOOM_THRESHOLD = 12;

const colors = { low: "#30d158", medium: "#ffd60a", high: "#ff453a", unknown: "#33789d" };
const trailColors = ["#267ca3", "#8753af", "#dc7136", "#2b9677", "#bf4d76"];
const VARIANTS: BusVariant[] = ["v1", "v2"];

function trailColor(id: string): string {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return trailColors[hash % trailColors.length];
}

const empty = (): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features: [] });

function routeFeatures(vehicles: Vehicle[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: vehicles.filter(v => v.trail.length > 1).map(vehicle => {
      return {
        type: "Feature",
        properties: { vehicleId: vehicle.id, color: trailColor(vehicle.id) },
        geometry: { type: "LineString", coordinates: vehicle.trail.map(p => [p.lng, p.lat]) }
      };
    })
  };
}

function problemFeatures(routes: RouteDef[], vehicles: Record<string, Vehicle>, selected: string | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.flatMap(route => {
      const vehicle = vehicles[route.vehicleId];
      if (!vehicle || !vehicle.targetStopId || !vehicle.risk || vehicle.risk === "low" || (selected && selected !== vehicle.id)) return [];
      const target = route.stops.findIndex(s => s.id === vehicle.targetStopId);
      if (target < 0) return [];
      const prior = route.stops.slice(0, target + 1);
      const closest = prior.reduce((best, stop, index) => {
        const d = (stop.position.lat - vehicle.position.lat) ** 2 + (stop.position.lng - vehicle.position.lng) ** 2;
        return d < best.distance ? { index, distance: d } : best;
      }, { index: 0, distance: Infinity }).index;
      const coords = [vehicle.position, ...route.stops.slice(closest + 1, target + 1).map(s => s.position)].map(p => [p.lng, p.lat]);
      if (coords.length < 2) coords.push([route.stops[target].position.lng, route.stops[target].position.lat]);
      return [{
        type: "Feature" as const,
        properties: { color: colors[vehicle.risk], vehicleId: vehicle.id },
        geometry: { type: "LineString" as const, coordinates: coords }
      }];
    })
  };
}

/**
 * Rasterizes the actual <BusTopIcon> component for map use. BusMap has no
 * bus geometry of its own — this is the only place it touches the shape,
 * and it does so by rendering the real component, not by re-implementing it.
 */
function busTopIconMarkup(variant: BusVariant, risk: RiskLevel): string {
  return renderToStaticMarkup(<BusTopIcon risk={risk} variant={variant} size={MAP_ICON_BASE_SIZE} />);
}

// Icon grows with zoom so the bus keeps a stable footprint relative to the map,
// instead of the old fixed 0.8 that stayed the same pixel size regardless of zoom.
const ICON_SIZE_EXPRESSION: maplibregl.ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"],
  ICON_ZOOM_THRESHOLD, 0.7,
  14, 1.0,
  16, 1.4,
  18, 1.9,
  20, 2.4
];

export function BusMap() {
  const routes = useDashboardStore((s) => s.routes);
  const vehicles = useDashboardStore((s) => s.vehicles);
  const selected = useDashboardStore((s) => s.selectedVehicleId);
  const filters = useDashboardStore((s) => s.filters);
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);

  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const fittedVehicles = useRef("");
  const [zoom, setZoom] = useState(13);

  const visible = useMemo(() => Object.values(vehicles).filter(v => {
    if (filters.routeIds && !filters.routeIds.includes(v.routeId)) return false;
    if (filters.riskLevels && (!v.risk || !filters.riskLevels.includes(v.risk))) return false;
    if (filters.onlyPredicted && v.predictedDelaySeconds === null) return false;
    const q = filters.query.trim().toLowerCase();
    return !q || `${v.id} ${v.garageNumber} ${v.routeId}`.toLowerCase().includes(q);
  }), [vehicles, filters]);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [37.6176, 55.7558],
      zoom: 11,
      attributionControl: false
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("zoom", () => setZoom(map.getZoom()));
    map.on("load", () => {
      // Register vector bus icon images for each variant x risk-color combination.
      // addImage must finish before the symbol layer that references these
      // image ids is added — otherwise maplibre drops the icons or throws
      // "styleimagemissing" on first paint. Wait on all of them explicitly
      // instead of firing addLayer right after the (async) loop starts.
      const imagesReady: Promise<void>[] = [];
      VARIANTS.forEach((variant) => {
        (Object.keys(colors) as (RiskLevel | "unknown")[]).forEach((risk) => {
          if (risk === "unknown") return;
          const svg = busTopIconMarkup(variant, risk);
          const dataUrl = `data:image/svg+xml;base64,${btoa(svg)}`;
          imagesReady.push(
            new Promise<void>((resolve) => {
              const img = new Image();
              img.onload = () => {
                if (!map.hasImage(`bus-${variant}-${risk}`)) {
                  map.addImage(`bus-${variant}-${risk}`, img, { pixelRatio: 2 });
                }
                resolve();
              };
              img.onerror = () => resolve(); // don't block the map forever on a bad icon
              img.src = dataUrl;
            })
          );
        });
      });

      map.addSource("routes", { type: "geojson", data: empty() });
      map.addLayer({ id: "routes", type: "line", source: "routes", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.85 } });
      map.addSource("problem", { type: "geojson", data: empty() });
      map.addLayer({ id: "problem-halo", type: "line", source: "problem", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 11, "line-opacity": 0.92 } });
      map.addLayer({ id: "problem", type: "line", source: "problem", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": 7, "line-opacity": 0.95, "line-dasharray": [1.2, 0.8] } });
      map.addSource("vehicles", { type: "geojson", data: empty() });
      // Circle markers at low zoom — don't depend on the bus images, safe to add now
      map.addLayer({ id: "vehicle-halo", type: "circle", source: "vehicles", paint: { "circle-radius": 15, "circle-color": "#ffffff", "circle-opacity": 0.96 }, filter: ["<", ["zoom"], ICON_ZOOM_THRESHOLD] });
      map.addLayer({ id: "vehicles", type: "circle", source: "vehicles", paint: { "circle-radius": ["case", ["get", "selected"], 11, 9], "circle-color": ["get", "color"], "circle-stroke-width": 2, "circle-stroke-color": "#ffffff" }, filter: ["<", ["zoom"], ICON_ZOOM_THRESHOLD] });
      map.addLayer({ id: "vehicle-label", type: "symbol", source: "vehicles", layout: { "text-field": ["get", "label"], "text-size": 11, "text-font": ["Noto Sans Bold"], "text-anchor": "top", "text-offset": [0, 1.5] }, paint: { "text-color": "#253b46", "text-halo-color": "#ffffff", "text-halo-width": 2 } });
      map.on("click", "vehicles", e => { const id = e.features?.[0]?.properties?.id; if (id) selectVehicle(String(id)); });
      map.on("mouseenter", "vehicles", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "vehicles", () => { map.getCanvas().style.cursor = ""; });

      // Vector bus icons at high zoom — added only once every bus image is
      // actually registered, so they're guaranteed to render on first paint.
      Promise.all(imagesReady).then(() => {
        map.addLayer({
          id: "vehicle-icons",
          type: "symbol",
          source: "vehicles",
          layout: {
            "icon-image": ["concat", "bus-", ["get", "variant"], "-", ["get", "riskKey"]],
            "icon-size": ICON_SIZE_EXPRESSION,
            "icon-rotate": ["get", "bearing"],
            "icon-rotation-alignment": "map",
            "icon-pitch-alignment": "map",
            "icon-allow-overlap": true,
            "visibility": "visible"
          },
          filter: [">=", ["zoom"], ICON_ZOOM_THRESHOLD]
        });
        map.on("click", "vehicle-icons", e => { const id = e.features?.[0]?.properties?.id; if (id) selectVehicle(String(id)); });
        map.on("mouseenter", "vehicle-icons", () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", "vehicle-icons", () => { map.getCanvas().style.cursor = ""; });
      });
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, [selectVehicle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      if (!map.getSource("vehicles")) return;
      const ids = new Set(visible.map(v => v.id));
      (map.getSource("routes") as maplibregl.GeoJSONSource).setData(routeFeatures(visible));
      (map.getSource("problem") as maplibregl.GeoJSONSource).setData(problemFeatures(routes.filter(r => ids.has(r.vehicleId)), vehicles, selected));
      (map.getSource("vehicles") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: visible.map(v => {
          // Calculate bearing from trail if not provided
          let bearing = v.bearing ?? 0;
          if (!v.bearing && v.trail.length >= 2) {
            const last = v.trail[v.trail.length - 1];
            const prev = v.trail[v.trail.length - 2];
            const dy = last.lat - prev.lat;
            const dx = last.lng - prev.lng;
            bearing = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
          }

          return {
            type: "Feature",
            properties: {
              id: v.id,
              label: zoom >= LABEL_ZOOM_THRESHOLD ? v.garageNumber : undefined,
              color: v.risk ? colors[v.risk] : trailColor(v.id),
              riskKey: v.risk || "low",
              variant: getBusVariant(v.id),
              bearing: bearing,
              selected: v.id === selected
            },
            geometry: { type: "Point", coordinates: [v.position.lng, v.position.lat] }
          };
        })
      });
      const activeVehicles = visible.map(v => v.id).sort().join("|");
      if (activeVehicles !== fittedVehicles.current && visible.length) {
        const bounds = new maplibregl.LngLatBounds();
        visible.forEach(v => bounds.extend([v.position.lng, v.position.lat]));
        if (visible.length === 1) map.easeTo({ center: [visible[0].position.lng, visible[0].position.lat], zoom: 14, duration: 500 });
        else map.fitBounds(bounds, { padding: 110, maxZoom: 14, duration: 500 });
        fittedVehicles.current = activeVehicles;
      }
      if (!visible.length) fittedVehicles.current = "";
    };
    if (map.isStyleLoaded()) update(); else map.once("load", update);
  }, [routes, vehicles, visible, selected, zoom]);

  useEffect(() => {
    const v = selected ? vehicles[selected] : null;
    if (v) mapRef.current?.easeTo({ center: [v.position.lng, v.position.lat], zoom: Math.max(mapRef.current.getZoom(), 14), duration: 500 });
  }, [selected, vehicles]);

  return <div ref={container} className="absolute inset-0" aria-label="Карта транспорта" />;
}