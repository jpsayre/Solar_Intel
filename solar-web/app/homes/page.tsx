"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";
const PAGE_SIZE = 25;
const FILTER_OPTIONS_LIMIT = 2000;

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

const ROOF_ORIENTATION_OPTIONS = ["East", "South", "West"] as const;

type FilterOptions = {
  counties: string[];
  cities: string[];
  subdivisions: string[];
};

function uniqueSorted(values: (string | null | undefined)[]): string[] {
  const set = new Set<string>();
  for (const v of values) {
    if (v != null && String(v).trim() !== "") set.add(String(v).trim());
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

export default function HomesPage() {
  const router = useRouter();

  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);

  const [county, setCounty] = useState("");
  const [city, setCity] = useState("");
  const [subdivision, setSubdivision] = useState("");
  const [roofOrientations, setRoofOrientations] = useState<string[]>([]);
  const [addressSearchInput, setAddressSearchInput] = useState("");
  const [addressSearchApplied, setAddressSearchApplied] = useState("");

  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    let alive = true;

    async function loadFilterOptions() {
      const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
      if (userErr || !userData.user) return;

      const { data, error } = await supabaseBrowser
        .from("homes")
        .select("county, city, subdivision_formatted")
        .limit(FILTER_OPTIONS_LIMIT);

      if (!alive) return;
      if (error) {
        console.error("Filter options error:", error);
        setFilterOptions({ counties: [], cities: [], subdivisions: [] });
        return;
      }

      const rows = (data ?? []) as {
        county?: string | null;
        city?: string | null;
        subdivision_formatted?: string | null;
      }[];
      setFilterOptions({
        counties: uniqueSorted(rows.map((r) => r.county)),
        cities: uniqueSorted(rows.map((r) => r.city)),
        subdivisions: uniqueSorted(rows.map((r) => r.subdivision_formatted)),
      });
    }

    loadFilterOptions();
    return () => {
      alive = false;
    };
  }, []);

  const loadRows = useCallback(async () => {
    setErr(null);
    setRows(null);

    const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
    if (userErr) {
      setErr(userErr.message);
      return;
    }
    if (!userData.user) {
      router.push("/login");
      return;
    }

    let query = supabaseBrowser
      .from("homes")
      .select("*")
      .order("index", { ascending: true })
      .limit(PAGE_SIZE);

    if (county) query = query.eq("county", county);
    if (city) query = query.eq("city", city);
    if (subdivision) query = query.eq("subdivision_formatted", subdivision);
    if (roofOrientations.length > 0) {
      const orClause = roofOrientations
        .map((o) => `qualified_orientations.ilike.%${o}%`)
        .join(",");
      query = query.or(orClause);
    }
    if (addressSearchApplied.trim()) {
      query = query.ilike("address", `%${addressSearchApplied.trim()}%`);
    }

    const { data, error } = await query;

    if (error) {
      setErr(error.message);
      setRows([]);
      return;
    }

    setRows((data ?? []) as HomeRow[]);
  }, [router, county, city, subdivision, roofOrientations, addressSearchApplied]);

  useEffect(() => {
    let alive = true;
    loadRows();
    return () => {
      alive = false;
    };
  }, [loadRows]);

  useEffect(() => {
    let alive = true;

    async function signImages() {
      if (!rows || rows.length === 0) return;

      const missing = rows
        .map((r) => r.original_index)
        .filter((oi) => imgUrls[oi] === undefined && imgErrors[oi] === undefined);

      if (missing.length === 0) return;

      const results = await Promise.all(
        missing.map(async (oi) => {
          const path = `${oi}.png`; // mapping you confirmed

          const { data, error } = await supabaseBrowser.storage
            .from(BUCKET)
            .createSignedUrl(path, 60 * 30); // 30 minutes

          if (error) {
            console.error("SIGNED URL ERROR (list)", { bucket: BUCKET, path, error });
            return { oi, url: "", errorMsg: error.message ?? "storage error" };
          }

          return { oi, url: data?.signedUrl ?? "", errorMsg: "" };
        })
      );

      if (!alive) return;

      const nextUrls = { ...imgUrls };
      const nextErrs = { ...imgErrors };

      for (const r of results) {
        if (r.url) nextUrls[r.oi] = r.url;
        else nextErrs[r.oi] = r.errorMsg || "missing image";
      }

      setImgUrls(nextUrls);
      setImgErrors(nextErrs);
    }

    signImages();

    return () => {
      alive = false;
    };
  }, [rows, imgUrls, imgErrors]);

  if (err) {
    return (
      <main className="min-h-screen px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-red-200 bg-red-50 px-6 py-4 text-red-800">
          <p className="font-medium">Something went wrong</p>
          <p className="mt-1 text-sm opacity-90">{err}</p>
        </div>
      </main>
    );
  }
  if (rows === null) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
          <p className="text-slate-600">Loading listings…</p>
        </div>
      </main>
    );
  }

  const applyFilters = () => {
    setAddressSearchApplied(addressSearchInput.trim());
  };

  const clearFilters = () => {
    setCounty("");
    setCity("");
    setSubdivision("");
    setRoofOrientations([]);
    setAddressSearchInput("");
    setAddressSearchApplied("");
  };

  const toggleRoofOrientation = (orientation: string) => {
    setRoofOrientations((prev) =>
      prev.includes(orientation) ? prev.filter((o) => o !== orientation) : [...prev, orientation]
    );
  };

  const hasActiveFilters =
    county ||
    city ||
    subdivision ||
    roofOrientations.length > 0 ||
    addressSearchInput.trim() ||
    addressSearchApplied;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Homes</h1>
          <button
            onClick={async () => {
              await supabaseBrowser.auth.signOut();
              router.push("/login");
            }}
            className="w-fit rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-800"
          >
            Log out
          </button>
        </header>

        <div className="mb-6 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-3 text-sm font-semibold text-slate-700">Filters</div>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_minmax(220px,auto)]">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-500">County</span>
                <select
                  value={county}
                  onChange={(e) => setCounty(e.target.value)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">All</option>
                  {(filterOptions?.counties ?? []).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-500">City</span>
                <select
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">All</option>
                  {(filterOptions?.cities ?? []).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-500">Subdivision</span>
                <select
                  value={subdivision}
                  onChange={(e) => setSubdivision(e.target.value)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">All</option>
                  {(filterOptions?.subdivisions ?? []).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex min-w-[220px] flex-col gap-1 overflow-visible">
                <span className="text-xs font-medium text-slate-500">Roof orientation</span>
                <div className="flex w-fit flex-row items-center gap-4 rounded-lg border border-neutral-200 bg-white px-4 py-2">
                  {ROOF_ORIENTATION_OPTIONS.map((orientation) => (
                    <label
                      key={orientation}
                      className="flex shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-slate-900"
                    >
                      <input
                        type="checkbox"
                        checked={roofOrientations.includes(orientation)}
                        onChange={() => toggleRoofOrientation(orientation)}
                        className="h-4 w-4 rounded border-neutral-300 text-amber-500 focus:ring-amber-400"
                      />
                      {orientation}
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">Address search</span>
              <div className="flex gap-2">
                <input
                  type="search"
                  placeholder="Search address…"
                  value={addressSearchInput}
                  onChange={(e) => setAddressSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && applyFilters()}
                  className="min-w-0 flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
                <button
                  type="button"
                  onClick={applyFilters}
                  className="shrink-0 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
                >
                  Search
                </button>
              </div>
            </div>
          </div>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="mt-3 text-sm font-medium text-slate-600 underline hover:text-slate-900"
            >
              Clear all filters
            </button>
          )}
        </div>

        <div className="flex flex-col gap-8">
          {rows.map((r) => {
            const url = imgUrls[r.original_index];
            const e = imgErrors[r.original_index];
            const imageUrl = url || "/window.svg";
            const imageAlt = url ? `Home ${r.original_index}` : e ? "No access / not found" : "Loading…";
            const { addressLine1, addressLine2, detailRows } = buildListingCardData(r);

            return (
              <Link
                key={r.index}
                href={`/homes/${encodeURIComponent(r.index)}`}
                className="block rounded-3xl text-inherit no-underline transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/60"
              >
                <ListingCard
                  addressLine1={addressLine1}
                  addressLine2={addressLine2}
                  imageUrl={imageUrl}
                  imageAlt={imageAlt}
                  rows={detailRows}
                />
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}
