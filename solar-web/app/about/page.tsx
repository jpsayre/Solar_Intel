"use client";

import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Solar Intelligence
        </h1>

        <p className="mt-8 text-slate-700">
          We analyze every home in the county to find those that meet our criteria*:
        </p>
        <ul className="mt-4 list-disc space-y-2 pl-6 text-slate-700">
          <li>Single family home</li>
          <li>Owner occupied</li>
          <li>No or minimal shade concerns</li>
          <li>No existing solar panel installation</li>
          <li>Roof segment a minimum of 30 m² (323 ft²) in the orientation(s) specified</li>
        </ul>
        <p className="mt-6 text-sm text-slate-500">
          * Based on public records and satellite imagery, actual conditions may vary.
        </p>
        <p className="mt-6 text-sm text-slate-500">
          Note: Inclusion on report does not indicate homeowner interest in a solar system or contact consent.
        </p>

        <div className="mt-10">
          <Link
            href="/homes"
            className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            View Homes
          </Link>
        </div>
      </div>
    </main>
  );
}
