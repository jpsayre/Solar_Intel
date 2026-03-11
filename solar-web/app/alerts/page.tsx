"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabaseBrowser } from "@/lib/supabase/client";

type PermitAlert = {
  id: number;
  home_index: string;
  address: string | null;
  city: string | null;
  permit_type: "solar" | "roof" | "battery" | "ev_charger";
  description: string | null;
  filed_date: string;
  valuation: number | null;
};

type FilterType = "all" | "solar" | "roof" | "battery" | "ev_charger";

const PERMIT_LABELS: Record<PermitAlert["permit_type"], string> = {
  solar: "Solar",
  roof: "Roof",
  battery: "Battery",
  ev_charger: "EV Charger",
};

const PERMIT_TAG_COLORS: Record<PermitAlert["permit_type"], string> = {
  solar: "bg-amber-100 text-amber-800",
  roof: "bg-blue-100 text-blue-700",
  battery: "bg-green-100 text-green-700",
  ev_charger: "bg-purple-100 text-purple-700",
};

function daysAgo(dateStr: string): number {
  const d = new Date(dateStr + "T00:00:00");
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

function formatValue(v: number | null): string {
  if (v == null) return "—";
  return "$" + v.toLocaleString();
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<PermitAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("all");

  useEffect(() => {
    let alive = true;
    async function load() {
      const { data, error } = await supabaseBrowser.rpc("get_recent_permits", {
        p_days: 90,
        p_types: ["solar", "roof", "battery", "ev_charger"],
        p_limit: 200,
      });
      if (!alive) return;
      if (error) {
        console.error("get_recent_permits error:", error);
        setLoading(false);
        return;
      }
      setAlerts((data ?? []) as PermitAlert[]);
      setLoading(false);
    }
    load();
    return () => { alive = false; };
  }, []);

  const filtered = alerts
    .filter((a) => filter === "all" || a.permit_type === filter)
    .sort((a, b) => daysAgo(a.filed_date) - daysAgo(b.filed_date));

  const solarCount = alerts.filter((a) => a.permit_type === "solar").length;
  const roofCount = alerts.filter((a) => a.permit_type === "roof").length;
  const batteryCount = alerts.filter((a) => a.permit_type === "battery").length;
  const evCount = alerts.filter((a) => a.permit_type === "ev_charger").length;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Permit Alerts
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Solar, roof, battery, and EV charger permits issued in the last 90 days.
          </p>
        </header>

        <div className="mb-6 flex flex-wrap items-center gap-2">
          {(
            [
              { key: "all", label: `All (${alerts.length})` },
              { key: "solar", label: `Solar (${solarCount})` },
              { key: "roof", label: `Roof (${roofCount})` },
              { key: "battery", label: `Battery (${batteryCount})` },
              { key: "ev_charger", label: `EV Charger (${evCount})` },
            ] as const
          ).map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setFilter(opt.key)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                filter === opt.key
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-neutral-200 bg-neutral-50/80 px-6 py-12 text-center text-slate-600">
            <p className="font-medium">No permits in the last 90 days</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {filtered.map((a) => {
              const days = daysAgo(a.filed_date);
              return (
                <Link
                  key={a.id}
                  href={`/homes/${encodeURIComponent(a.home_index)}?from=alerts`}
                  className="group block rounded-xl border border-neutral-200 bg-white px-5 py-4 text-inherit no-underline transition-all hover:border-slate-300 hover:shadow-md hover:shadow-slate-100/60"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${PERMIT_TAG_COLORS[a.permit_type]}`}
                        >
                          {PERMIT_LABELS[a.permit_type]}
                        </span>
                        <span className="text-xs text-slate-400">
                          {days === 0
                            ? "Today"
                            : days === 1
                            ? "Yesterday"
                            : `${days} days ago`}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm font-semibold text-slate-900 group-hover:text-amber-700">
                        {a.address ?? a.home_index}
                        {a.city ? `, ${a.city}` : ""}
                      </p>
                      {a.description && (
                        <p className="mt-0.5 text-sm text-slate-600">
                          {a.description}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-sm font-semibold text-slate-900">
                        {formatValue(a.valuation)}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-400">
                        {a.filed_date}
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
