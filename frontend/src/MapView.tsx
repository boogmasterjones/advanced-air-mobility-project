import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { Facility } from "./api";

// OpenStreetMap raster tiles, no key. Fine for a prototype; respect the tile usage policy.
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export default function MapView({ origin, dest }: { origin?: Facility; dest?: Facility }) {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!ref.current || map.current) return;
    map.current = new maplibregl.Map({ container: ref.current, style: STYLE, center: [-81.5, 27.8], zoom: 6 });
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    const pts = [origin, dest].filter(Boolean) as Facility[];
    pts.forEach((p, i) =>
      markers.current.push(
        new maplibregl.Marker({ color: i === 0 ? "#b3410d" : "#0c6b63" })
          .setLngLat([p.lon, p.lat])
          .setPopup(new maplibregl.Popup().setText(p.name))
          .addTo(m),
      ),
    );
    const draw = () => {
      if (m.getSource("route")) { m.removeLayer("route"); m.removeSource("route"); }
      if (pts.length === 2) {
        m.addSource("route", {
          type: "geojson",
          data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: pts.map((p) => [p.lon, p.lat]) } },
        });
        m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#334", "line-width": 3, "line-dasharray": [2, 2] } });
        m.fitBounds([[Math.min(...pts.map((p) => p.lon)), Math.min(...pts.map((p) => p.lat))],
                     [Math.max(...pts.map((p) => p.lon)), Math.max(...pts.map((p) => p.lat))]], { padding: 80, maxZoom: 10 });
      }
    };
    m.loaded() ? draw() : m.once("load", draw);
  }, [origin, dest]);

  return <div ref={ref} className="map" />;
}
