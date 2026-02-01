"use client";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

export type MapPoint = {
  lat: number;
  lng: number;
  index: string;
  address: string;
};

const ORANGE = "#f59e0b";
const DEFAULT_CENTER: [number, number] = [39.7, -105.0];
const DEFAULT_ZOOM = 10;

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

type HomeMapProps = {
  points: MapPoint[];
};

export default function HomeMap({ points }: HomeMapProps) {
  const pointsList = useMemo(
    () => points.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng)),
    [points]
  );

  if (pointsList.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center rounded-2xl border border-neutral-200 bg-neutral-50 text-sm text-slate-500">
        No locations to show. Adjust filters or add homes with latitude/longitude.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm [&_.leaflet-interactive]:cursor-pointer">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        className="h-[320px] w-full"
        scrollWheelZoom={true}
        style={{ minHeight: 320 }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={pointsList} />
        {pointsList.map((p) => (
          <CircleMarker
            key={p.index}
            center={[p.lat, p.lng]}
            radius={8}
            pathOptions={{
              color: ORANGE,
              fillColor: ORANGE,
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
              {p.address}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
