"use client";

import { useState } from "react";
import Link from "next/link";

type PermitAlert = {
  id: string;
  homeIndex: string;
  address: string;
  permitType: "solar" | "roof" | "battery" | "ev_charger";
  description: string;
  issueDate: string;
  daysAgo: number;
  value: string;
};

const NOW = new Date();
function daysAgoDate(days: number): string {
  const d = new Date(NOW);
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const FAKE_ALERTS: PermitAlert[] = [
  { id: "1", homeIndex: "BOULDER_CO_4821", address: "1432 Alpine Ave, Boulder", permitType: "solar", description: "Residential solar PV installation — 8.4 kW rooftop system", issueDate: daysAgoDate(2), daysAgo: 2, value: "$22,400" },
  { id: "2", homeIndex: "BOULDER_CO_10293", address: "2875 Mapleton Ave, Boulder", permitType: "roof", description: "Full roof replacement — composite shingles, 28 sq", issueDate: daysAgoDate(4), daysAgo: 4, value: "$14,200" },
  { id: "3", homeIndex: "BOULDER_CO_7514", address: "905 Baseline Rd, Boulder", permitType: "solar", description: "Solar PV system with battery storage — 10.2 kW + 13.5 kWh", issueDate: daysAgoDate(5), daysAgo: 5, value: "$38,900" },
  { id: "4", homeIndex: "BOULDER_CO_3387", address: "4410 Darley Ave, Boulder", permitType: "roof", description: "Partial re-roof — south-facing slope, architectural shingles", issueDate: daysAgoDate(8), daysAgo: 8, value: "$6,800" },
  { id: "5", homeIndex: "BOULDER_CO_15602", address: "620 Concord Ave, Boulder", permitType: "solar", description: "Residential solar PV — 6.0 kW ground-mount system", issueDate: daysAgoDate(10), daysAgo: 10, value: "$18,200" },
  { id: "6", homeIndex: "BOULDER_CO_8841", address: "3200 Oneal Pkwy, Boulder", permitType: "roof", description: "Full roof replacement — standing seam metal, 32 sq", issueDate: daysAgoDate(12), daysAgo: 12, value: "$24,500" },
  { id: "7", homeIndex: "BOULDER_CO_1198", address: "1780 Sumac Ave, Boulder", permitType: "solar", description: "Solar PV installation — 12.6 kW with microinverters", issueDate: daysAgoDate(14), daysAgo: 14, value: "$31,500" },
  { id: "8", homeIndex: "BOULDER_CO_6450", address: "540 Manhattan Dr, Boulder", permitType: "roof", description: "Roof replacement — impact-resistant shingles, 24 sq", issueDate: daysAgoDate(18), daysAgo: 18, value: "$16,900" },
  { id: "9", homeIndex: "BOULDER_CO_11920", address: "2105 Balsam Dr, Boulder", permitType: "solar", description: "Residential solar PV — 9.8 kW rooftop, south/west split", issueDate: daysAgoDate(21), daysAgo: 21, value: "$26,100" },
  { id: "10", homeIndex: "BOULDER_CO_2044", address: "855 35th St, Boulder", permitType: "roof", description: "Full tear-off and re-roof — synthetic slate tiles", issueDate: daysAgoDate(25), daysAgo: 25, value: "$32,000" },
  { id: "11", homeIndex: "BOULDER_CO_13775", address: "4685 Baseline Rd, Boulder", permitType: "solar", description: "Solar PV system — 7.2 kW with optimizers", issueDate: daysAgoDate(27), daysAgo: 27, value: "$19,800" },
  { id: "12", homeIndex: "BOULDER_CO_950", address: "1220 Cedar Ave, Boulder", permitType: "roof", description: "Roof replacement — asphalt shingles, 22 sq, new underlayment", issueDate: daysAgoDate(29), daysAgo: 29, value: "$11,400" },
  { id: "13", homeIndex: "BOULDER_CO_5230", address: "3050 5th St, Boulder", permitType: "battery", description: "Tesla Powerwall 3 installation — 13.5 kWh residential battery", issueDate: daysAgoDate(3), daysAgo: 3, value: "$12,500" },
  { id: "14", homeIndex: "BOULDER_CO_9102", address: "1605 Cascade Ave, Boulder", permitType: "ev_charger", description: "Level 2 EV charger — 240V / 48A hardwired, garage mount", issueDate: daysAgoDate(6), daysAgo: 6, value: "$3,800" },
  { id: "15", homeIndex: "BOULDER_CO_7781", address: "4220 Aurora Ave, Boulder", permitType: "battery", description: "Enphase IQ Battery 5P — 2x units, 10 kWh total", issueDate: daysAgoDate(11), daysAgo: 11, value: "$16,200" },
  { id: "16", homeIndex: "BOULDER_CO_14550", address: "890 University Ave, Boulder", permitType: "ev_charger", description: "ChargePoint Home Flex — 50A circuit, outdoor pedestal", issueDate: daysAgoDate(15), daysAgo: 15, value: "$4,100" },
  { id: "17", homeIndex: "BOULDER_CO_2290", address: "2340 Spruce St, Boulder", permitType: "battery", description: "Generac PWRcell — 18 kWh whole-home battery backup", issueDate: daysAgoDate(19), daysAgo: 19, value: "$19,800" },
  { id: "18", homeIndex: "BOULDER_CO_11400", address: "1055 Moorhead Ave, Boulder", permitType: "ev_charger", description: "Wallbox Pulsar Plus — 240V / 40A, indoor garage install", issueDate: daysAgoDate(23), daysAgo: 23, value: "$3,200" },
];

type FilterType = "all" | "solar" | "roof" | "battery" | "ev_charger";

const PERMIT_LABELS: Record<PermitAlert["permitType"], string> = {
  solar: "Solar",
  roof: "Roof",
  battery: "Battery",
  ev_charger: "EV Charger",
};

const PERMIT_TAG_COLORS: Record<PermitAlert["permitType"], string> = {
  solar: "bg-amber-100 text-amber-800",
  roof: "bg-blue-100 text-blue-700",
  battery: "bg-green-100 text-green-700",
  ev_charger: "bg-purple-100 text-purple-700",
};

export default function AlertsPage() {
  const [filter, setFilter] = useState<FilterType>("all");

  const filtered = FAKE_ALERTS
    .filter((a) => filter === "all" || a.permitType === filter)
    .sort((a, b) => a.daysAgo - b.daysAgo);

  const solarCount = FAKE_ALERTS.filter((a) => a.permitType === "solar").length;
  const roofCount = FAKE_ALERTS.filter((a) => a.permitType === "roof").length;
  const batteryCount = FAKE_ALERTS.filter((a) => a.permitType === "battery").length;
  const evCount = FAKE_ALERTS.filter((a) => a.permitType === "ev_charger").length;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Permit Alerts
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Solar, roof, battery, and EV charger permits issued in the last 30 days.
          </p>
        </header>

        <div className="mb-6 flex flex-wrap items-center gap-2">
          {(
            [
              { key: "all", label: `All (${FAKE_ALERTS.length})` },
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

        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-neutral-200 bg-neutral-50/80 px-6 py-12 text-center text-slate-600">
            <p className="font-medium">No permits match the filter</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {filtered.map((a) => (
              <Link
                key={a.id}
                href={`/homes/${encodeURIComponent(a.homeIndex)}?from=alerts`}
                className="group block rounded-xl border border-neutral-200 bg-white px-5 py-4 text-inherit no-underline transition-all hover:border-slate-300 hover:shadow-md hover:shadow-slate-100/60"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${PERMIT_TAG_COLORS[a.permitType]}`}
                      >
                        {PERMIT_LABELS[a.permitType]}
                      </span>
                      <span className="text-xs text-slate-400">
                        {a.daysAgo === 0
                          ? "Today"
                          : a.daysAgo === 1
                          ? "Yesterday"
                          : `${a.daysAgo} days ago`}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm font-semibold text-slate-900 group-hover:text-amber-700">
                      {a.address}
                    </p>
                    <p className="mt-0.5 text-sm text-slate-600">
                      {a.description}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-sm font-semibold text-slate-900">
                      {a.value}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {a.issueDate}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
