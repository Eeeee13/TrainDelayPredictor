import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useDashboardStore } from "@/store/dashboardStore";
import { MAP_CENTER } from "@/mocks/network";
import { MAP_STYLE_URL, MAP_ATTRIBUTION } from "@/config/mapConfig";

const LABEL_ZOOM_THRESHOLD = 15;

export function BusMap() {
  const routes = useDashboardStore((s) => s.routes);
  const vehicles = useDashboardStore((s) => s.vehicles);
  const selectedRouteId = useDashboardStore((s) => s.selectedRouteId);
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);
  const selectRoute = useDashboardStore((s) => s.selectRoute);
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);
  const filters = useDashboardStore((s) => s.filters);
  const theme = useDashboardStore((s) => s.theme);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [zoom, setZoom] = useState(13);

  const allVehicles = useMemo(() => Object.values(vehicles), [vehicles]);

  const filteredVehicles = useMemo(
    () =>
      allVehicles.filter((v) => {
        if (selectedRouteId && v.routeId !== selectedRouteId) return false;
        if (filters.riskLevels && !filters.riskLevels.includes(v.risk)) return false;
        if (filters.depots && !filters.depots.includes(v.depot)) return false;
        return true;
      }),
    [allVehicles, selectedRouteId, filters]
  );

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: MAP_STYLE_URL[theme],
      center: [MAP_CENTER.lng, MAP_CENTER.lat],
      zoom: 13
    });

    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    map.on("zoom", () => setZoom(map.getZoom()));
    map.on("click", () => {
      selectRoute(null);
      selectVehicle(null);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.setStyle(MAP_STYLE_URL[theme]);
    }
  }, [theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateRoutes = () => {
      if (map.getSource("routes")) {
        (map.getSource("routes") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: routes.map((route) => ({
            type: "Feature",
            id: route.id,
            properties: {
              id: route.id,
              color: route.color,
              isSelected: selectedRouteId === route.id,
              isDim: selectedRouteId !== null && selectedRouteId !== route.id
            },
            geometry: {
              type: "LineString",
              coordinates: route.path.map((p) => [p.lng, p.lat])
            }
          }))
        });
      }
    };

    const updateVehicles = () => {
      if (map.getSource("vehicles")) {
        (map.getSource("vehicles") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: filteredVehicles.map((vehicle) => {
            const route = routes.find((r) => r.id === vehicle.routeId);
            return {
              type: "Feature",
              id: vehicle.id,
              properties: {
                id: vehicle.id,
                heading: vehicle.heading,
                risk: vehicle.risk,
                isSelected: vehicle.id === selectedVehicleId,
                dimmed: selectedRouteId !== null && vehicle.routeId !== selectedRouteId,
                label: zoom >= LABEL_ZOOM_THRESHOLD ? route?.shortName ?? vehicle.garageNumber : undefined
              },
              geometry: {
                type: "Point",
                coordinates: [vehicle.position.lng, vehicle.position.lat]
              }
            };
          })
        });
      }
    };

    if (map.isStyleLoaded()) {
      updateRoutes();
      updateVehicles();
    } else {
      map.on("load", () => {
        // Add routes layer
        if (!map.getSource("routes")) {
          map.addSource("routes", {
            type: "geojson",
            data: {
              type: "FeatureCollection",
              features: []
            }
          });

          map.addLayer({
            id: "routes",
            type: "line",
            source: "routes",
            layout: { "line-join": "round", "line-cap": "round" },
            paint: {
              "line-color": ["get", "color"],
              "line-width": ["case", ["get", "isSelected"], 4, 2],
              "line-opacity": ["case", ["get", "isDim"], 0.1, ["case", ["get", "isSelected"], 0.95, 0.38]]
            }
          });

          map.on("click", "routes", (e: maplibregl.MapLayerMouseEvent) => {
            const props = e.features?.[0]?.properties as { id: string; isSelected: boolean };
            if (props) {
              selectRoute(props.isSelected ? null : props.id);
            }
          });

          map.on("mouseenter", "routes", () => map.getCanvas().style.cursor = "pointer");
          map.on("mouseleave", "routes", () => map.getCanvas().style.cursor = "");
        }

        // Add vehicles layer
        if (!map.getSource("vehicles")) {
          map.addSource("vehicles", {
            type: "geojson",
            data: {
              type: "FeatureCollection",
              features: []
            }
          });

          map.addLayer({
            id: "vehicles",
            type: "circle",
            source: "vehicles",
            paint: {
              "circle-radius": 8,
              "circle-color": ["case", ["get", "isSelected"], "#ffffff", ["get", "dimmed"], "#666666", "#3b82f6"],
              "circle-stroke-width": 2,
              "circle-stroke-color": ["case", ["get", "isSelected"], "#3b82f6", ["get", "dimmed"], "#444444", "#ffffff"]
            }
          });

          map.on("click", "vehicles", (e: maplibregl.MapLayerMouseEvent) => {
            const props = e.features?.[0]?.properties as { id: string; isSelected: boolean };
            if (props) {
              selectVehicle(props.isSelected ? null : props.id);
            }
          });

          map.on("mouseenter", "vehicles", () => map.getCanvas().style.cursor = "pointer");
          map.on("mouseleave", "vehicles", () => map.getCanvas().style.cursor = "");
        }

        updateRoutes();
        updateVehicles();
      });
    }
  }, [routes, filteredVehicles, selectedRouteId, selectedVehicleId, zoom]);

  return <div ref={mapContainerRef} className="absolute inset-0" />;
}
