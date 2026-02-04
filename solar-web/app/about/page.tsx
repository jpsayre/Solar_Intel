"use client";

import Image from "next/image";
import Link from "next/link";

function getCompassImageUrl() {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!base) return "";
  return `${base}/storage/v1/object/public/site_images/Compass.png`;
}

function getMapChartImageUrl() {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!base) return "";
  return `${base}/storage/v1/object/public/site_images/MapChart_Map.png`;
}

export default function AboutPage() {
  const compassUrl = getCompassImageUrl();
  const mapChartUrl = getMapChartImageUrl();

  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-2xl">
        <div className="flex justify-between items-start gap-4">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Solar Intelligence
          </h1>
          <Link
            href="/homes"
            className="shrink-0 inline-flex items-center justify-center rounded-xl bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Roof Explorer
          </Link>
        </div>

        <p className="mt-8 text-slate-700">
          We use public records and satellite imagery to find the homes that meet our criteria*:
        </p>
        <ul className="mt-4 list-disc space-y-2 pl-6 text-slate-700">
          <li>Single family home</li>
          <li>Owner occupied</li>
          <li>No or minimal shade concerns</li>
          <li>No existing solar panel installation</li>
          <li>Roof segment a minimum of 30 m² (323 ft²) in the orientation(s) specified</li>
        </ul>
        <p className="mt-6 text-sm text-slate-500">
          * Data changes over time, imagery analysis is impacted by image quality. Actual conditions may vary.
        </p>
        <p className="mt-6 text-sm text-slate-500">
          Note: Inclusion on report does not indicate homeowner interest in a solar system or contact consent.
        </p>

        <div className="mt-10">
          {compassUrl ? (
            <Image
              src={compassUrl}
              alt="Compass"
              width={400}
              height={400}
              className="rounded-lg object-contain"
              unoptimized
            />
          ) : (
            <div className="flex h-[200px] w-[200px] items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500">
              Compass
            </div>
          )}
          <p className="mt-3 text-sm text-slate-600">
            East Facing: 80–140°, South Facing: 140–220°, West Facing: 220–280°
          </p>
        </div>

        <div className="mt-14">
          <h2 className="text-xl font-semibold text-slate-900">Currently Supported Counties (More Coming Soon!)</h2>
          {mapChartUrl ? (
            <Image
              src={mapChartUrl}
              alt="Counties"
              width={800}
              height={500}
              className="mt-4 w-full rounded-lg object-contain"
              unoptimized
            />
          ) : (
            <div className="mt-4 flex h-[300px] w-full items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500">
              Map Chart
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
