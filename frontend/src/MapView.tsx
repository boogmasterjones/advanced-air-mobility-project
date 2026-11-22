import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { placeName, type Facility, type MapData } from "./api";

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
const GROUND = "#0c6b63";
const AIR = "#b3410d";

type Line = [number, number][];
const feature = (coordinates: Line): GeoJSON.Feature => ({
  type: "Feature", properties: {}, geometry: { type: "LineString", coordinates },
});

export default function MapView({ origin, dest, map }: { origin?: Facility; dest?: Facility; map: MapData | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const m = new maplibregl.Map({ container: ref.current, style: STYLE, center: [-81.5, 27.8], zoom: 6 });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = m;
    return () => { m.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const m = mapRef.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    const pin = (lon: number, lat: number, color: string, label: string) =>
      markers.current.push(new maplibregl.Marker({ color }).setLngLat([lon, lat])
        .setPopup(new maplibregl.Popup({ offset: 24 }).setText(label)).addTo(m));
    if (origin) pin(origin.lon, origin.lat, AIR, `From: ${placeName(origin)}`);
    if (dest) pin(dest.lon, dest.lat, GROUND, `To: ${placeName(dest)}`);
    if (map) pin(map.air_base.lon, map.air_base.lat, "#6b7280", `Simulated aircraft base: ${map.air_base.name}`);

    const straight: Line = origin && dest ? [[origin.lon, origin.lat], [dest.lon, dest.lat]] : [];
    const road: Line = map && map.road.length > 1 ? map.road : [];
    const air: Line = map ? map.air : straight;
    const draw = () => {
      const set = (id: string, line: Line, paint: maplibregl.LineLayerSpecification["paint"]) => {
        const data = feature(line.length > 1 ? line : []);
        const src = m.getSource(id) as maplibregl.GeoJSONSource | undefined;
        if (src) src.setData(data);
        else {
          m.addSource(id, { type: "geojson", data });
          m.addLayer({ id, type: "line", source: id, paint, layout: { "line-cap": "round", "line-join": "round" } });
        }
      };
      set("road", road, { "line-color": GROUND, "line-width": 4, "line-opacity": 0.85 });
      set("air", air, { "line-color": AIR, "line-width": 3, "line-dasharray": [2, 2] });
      const pts = [...road, ...air];
      if (pts.length > 1) {
        const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
        m.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
          { padding: 60, maxZoom: 11, duration: 400 });
      }
    };
    if (m.isStyleLoaded()) draw(); else m.once("load", draw);
  }, [origin, dest, map]);

  return (
    <div className="map-wrap">
      <div ref={ref} className="map" role="img" aria-label="Map of the trip" />
      <p className="legend">
        <span><i className="swatch line" style={{ background: GROUND }} /> Road route{map && !map.road_is_routed ? " (not available, time is modeled)" : ""}</span>
        <span><i className="swatch dash" style={{ borderColor: AIR }} /> Flight path, from the simulated base</span>
      </p>
    </div>
  );
}
