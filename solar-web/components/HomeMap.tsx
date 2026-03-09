"use client";

import L from "leaflet";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import "leaflet/dist/leaflet.css";
import "react-leaflet-cluster/dist/assets/MarkerCluster.css";
import "react-leaflet-cluster/dist/assets/MarkerCluster.Default.css";

export type MapPoint = {
  lat: number;
  lng: number;
  index: string;
  address: string;
  score: number | null;
  roofScore: number | null;
};

export type MapBounds = {
  north: number;
  south: number;
  east: number;
  west: number;
};

const DEFAULT_CENTER: [number, number] = [39.7, -105.0];
const DEFAULT_ZOOM = 10;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function createGrayClusterIcon(cluster: any) {
  const count = cluster.getChildCount();
  return L.divIcon({
    html: `<div style="background:rgba(156,163,175,0.75);color:#fff;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;border:2px solid rgba(107,114,128,0.6)">${count}</div>`,
    className: "",
    iconSize: L.point(36, 36),
  });
}

/** Interpolate from blue (score=0) to red (score=100) via HSL. */
function scoreToColor(score: number | null): string {
  if (score == null) return "#9ca3af"; // gray for no score
  const clamped = Math.max(0, Math.min(100, score));
  // hue: 240 (blue) at 0, 0 (red) at 100
  const hue = 240 - (clamped / 100) * 240;
  return `hsl(${hue}, 85%, 50%)`;
}

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMap();

  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 14);
      return;
    }
    const bounds = L.latLngBounds(
      points.map((p) => [p.lat, p.lng] as [number, number])
    );
    map.fitBounds(bounds, { padding: [48, 48], maxZoom: 15 });
  }, [map, points]);

  return null;
}

function SetInitialView({
  center,
  zoom,
}: {
  center: [number, number];
  zoom: number;
}) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom);
  }, [map, center, zoom]);
  return null;
}

function MapBoundsReporter({
  onBoundsChange,
  onViewChange,
}: {
  onBoundsChange: (bounds: MapBounds | null) => void;
  onViewChange?: (center: [number, number], zoom: number) => void;
}) {
  const map = useMap();
  const boundsRef = useRef(onBoundsChange);
  boundsRef.current = onBoundsChange;
  const viewRef = useRef(onViewChange);
  viewRef.current = onViewChange;

  useEffect(() => {
    const report = () => {
      const b = map.getBounds();
      if (!b.isValid()) {
        boundsRef.current(null);
        return;
      }
      boundsRef.current({
        north: b.getNorth(),
        south: b.getSouth(),
        east: b.getEast(),
        west: b.getWest(),
      });
      const c = map.getCenter();
      const z = map.getZoom();
      viewRef.current?.([c.lat, c.lng], z);
    };

    report();
    map.on("moveend", report);
    return () => {
      map.off("moveend", report);
    };
  }, [map]);

  return null;
}

type HomeMapProps = {
  points: MapPoint[];
  initialCenter?: [number, number] | null;
  initialZoom?: number | null;
  onBoundsChange?: (bounds: MapBounds | null) => void;
  onViewChange?: (center: [number, number], zoom: number) => void;
};

export default function HomeMap({
  points,
  initialCenter,
  initialZoom,
  onBoundsChange,
  onViewChange,
}: HomeMapProps) {
  const pointsList = useMemo(
    () => points.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng)),
    [points]
  );

  const hasInitialView =
    initialCenter != null &&
    initialZoom != null &&
    Number.isFinite(initialCenter[0]) &&
    Number.isFinite(initialCenter[1]) &&
    Number.isFinite(initialZoom);

  if (pointsList.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center rounded-2xl border border-neutral-200 bg-neutral-50 text-sm text-slate-500">
        No locations to show. Adjust filters or add homes with latitude/longitude.
      </div>
    );
  }

  return (
    <div className="relative z-0 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm [&_.leaflet-interactive]:cursor-pointer">
      <MapContainer
        center={hasInitialView ? initialCenter! : DEFAULT_CENTER}
        zoom={hasInitialView ? initialZoom! : DEFAULT_ZOOM}
        className="h-[320px] w-full"
        scrollWheelZoom={true}
        style={{ minHeight: 320 }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {hasInitialView ? (
          <SetInitialView center={initialCenter!} zoom={initialZoom!} />
        ) : (
          <FitBounds points={pointsList} />
        )}
        {onBoundsChange ? (
          <MapBoundsReporter onBoundsChange={onBoundsChange} onViewChange={onViewChange} />
        ) : null}
        <MarkerClusterGroup chunkedLoading disableClusteringAtZoom={13} maxClusterRadius={40} iconCreateFunction={createGrayClusterIcon}>
          {pointsList.map((p) => {
            const color = scoreToColor(p.score);
            return (
            <CircleMarker
              key={p.index}
              center={[p.lat, p.lng]}
              radius={8}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: 1,
                weight: 2,
              }}
              eventHandlers={{
                click: () => {
                  window.location.href = `/homes/${encodeURIComponent(p.index)}`;
                },
              }}
            >
              <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
                <div>
                  <div>{p.address}</div>
                  <div style={{ fontSize: 11, opacity: 0.85 }}>
                    Ranking: {p.score != null ? Number(p.score.toFixed(1)) : "—"} · Roof: {p.roofScore != null ? Number(p.roofScore.toFixed(1)) : "—"}
                  </div>
                </div>
              </Tooltip>
            </CircleMarker>
            );
          })}
        </MarkerClusterGroup>
      </MapContainer>
    </div>
  );
}
