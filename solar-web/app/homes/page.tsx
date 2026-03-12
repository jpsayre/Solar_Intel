"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import { indexToImagePath } from "@/lib/imagePath";
import ListingCard from "@/components/ListingCard";
import type { MapBounds } from "@/components/HomeMap";

const HOMES_PATH = "/homes";

function parseFloatParam(value: string | null): number | null {
  if (value == null || value === "") return null;
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function buildHomesSearchParams(params: {
  county?: string;
  city?: string;
  subdivision?: string;
  address?: string;
  lat?: number | null;
  lng?: number | null;
  zoom?: number | null;
  sortBy?: string;
  minModel?: string;
  minRoof?: string;
  minSolar?: string;
  minBattery?: string;
  tag?: string;
  excludeTag?: string;
  excludeDnc?: boolean;
  showSolar?: boolean;
}): URLSearchParams {
  const sp = new URLSearchParams();
  if (params.county?.trim()) sp.set("county", params.county.trim());
  if (params.city?.trim()) sp.set("city", params.city.trim());
  if (params.subdivision?.trim()) sp.set("subdivision", params.subdivision.trim());
  if (params.address?.trim()) sp.set("address", params.address.trim());
  if (params.lat != null && Number.isFinite(params.lat)) sp.set("lat", String(params.lat));
  if (params.lng != null && Number.isFinite(params.lng)) sp.set("lng", String(Math.round(params.lng)));
  if (params.zoom != null && Number.isFinite(params.zoom)) sp.set("zoom", String(Math.round(params.zoom)));
  if (params.sortBy && params.sortBy !== "hybrid") sp.set("sort", params.sortBy);
  if (params.minModel?.trim()) sp.set("minModel", params.minModel.trim());
  if (params.minRoof?.trim()) sp.set("minRoof", params.minRoof.trim());
  if (params.minSolar?.trim()) sp.set("minSolar", params.minSolar.trim());
  if (params.minBattery?.trim()) sp.set("minBattery", params.minBattery.trim());
  if (params.tag?.trim()) sp.set("tag", params.tag.trim());
  if (params.excludeTag?.trim()) sp.set("excludeTag", params.excludeTag.trim());
  if (params.excludeDnc === false) sp.set("dnc", "0");
  if (params.showSolar) sp.set("solar", "1");
  return sp;
}

const HomeMap = dynamic(() => import("@/components/HomeMap"), { ssr: false });

const BUCKET = "images";
const PAGE_SIZE = 100;
const NEXT_PAGE_SIZE = 100;
const FILTER_OPTIONS_LIMIT = 2000;
const MAP_POINTS_LIMIT = 1000;

type HomeRow = {
  index: string;
  original_index: number;
  model_score?: number | null;
  roof_score?: number | null;
  has_solar?: boolean;
  [key: string]: unknown;
};

type SortOption = "model_score" | "roof_score" | "hybrid";
const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "model_score", label: "Ranking score" },
  { value: "roof_score", label: "Roof score" },
  { value: "hybrid", label: "Hybrid" },
];

const INTEREST_OPTIONS = ["", "Cold", "Cool", "Warm", "Hot"] as const;
const INTEREST_RANK: Record<string, number> = { "Cold": 1, "Cool": 2, "Warm": 3, "Hot": 4 };

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

function HomesPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);

  const [county, setCounty] = useState(() => searchParams.get("county") ?? "");
  const [city, setCity] = useState(() => searchParams.get("city") ?? "");
  const [subdivision, setSubdivision] = useState(() => searchParams.get("subdivision") ?? "");
  const [addressSearchInput, setAddressSearchInput] = useState(() => searchParams.get("address") ?? "");
  const [addressSearchApplied, setAddressSearchApplied] = useState(() => searchParams.get("address") ?? "");
  const [mapBounds, setMapBounds] = useState<MapBounds | null>(null);

  const [mapCenter, setMapCenter] = useState<[number, number] | null>(() => {
    const lat = parseFloatParam(searchParams.get("lat"));
    const lng = parseFloatParam(searchParams.get("lng"));
    return lat != null && lng != null ? [lat, lng] : null;
  });
  const [mapZoom, setMapZoom] = useState<number | null>(() => parseFloatParam(searchParams.get("zoom")));

  const initialMapViewRef = useRef<{ center: [number, number]; zoom: number } | null>(null);
  if (initialMapViewRef.current === null) {
    const lat = parseFloatParam(searchParams.get("lat"));
    const lng = parseFloatParam(searchParams.get("lng"));
    const z = parseFloatParam(searchParams.get("zoom"));
    if (lat != null && lng != null && z != null) {
      initialMapViewRef.current = { center: [lat, lng], zoom: z };
    }
  }

  const [offset, setOffset] = useState(PAGE_SIZE);
  const [hasMore, setHasMore] = useState(false);
  const [boundsLoading, setBoundsLoading] = useState(false);

  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});

  const [sortBy, setSortBy] = useState<SortOption>(() => (searchParams.get("sort") as SortOption) || "hybrid");
  const [minModelScore, setMinModelScore] = useState(() => searchParams.get("minModel") ?? "");
  const [minRoofScore, setMinRoofScore] = useState(() => searchParams.get("minRoof") ?? "");
  const [minSolarInterest, setMinSolarInterest] = useState(() => searchParams.get("minSolar") ?? "");
  const [minBatteryInterest, setMinBatteryInterest] = useState(() => searchParams.get("minBattery") ?? "");

  const [followedHomeIndices, setFollowedHomeIndices] = useState<Set<string>>(new Set());
  const [userId, setUserId] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgHomeByIndex, setOrgHomeByIndex] = useState<Record<string, { tags: string[]; interest_in_solar: string | null; interest_in_battery: string | null; do_not_contact: boolean }>>({});
  const [tagFilter, setTagFilter] = useState(() => searchParams.get("tag") ?? "");
  const [excludeTagFilter, setExcludeTagFilter] = useState(() => searchParams.get("excludeTag") ?? "");
  const [excludeDoNotContact, setExcludeDoNotContact] = useState(() => searchParams.get("dnc") !== "0");
  const [showSolarHomes, setShowSolarHomes] = useState(() => searchParams.get("solar") === "1");
  const [totalCount, setTotalCount] = useState<number | null>(null);

  // Lightweight map points from RPC (scores pre-joined, no gray flash)
  type RpcMapPoint = { index: string; latitude: number; longitude: number; model_score: number | null; roof_score: number | null; hybrid_score: number | null };
  const [rpcMapPoints, setRpcMapPoints] = useState<RpcMapPoint[] | null>(null);
  const rpcRequestRef = useRef(0); // track latest RPC request to ignore stale responses

  // Load map points (no debounce here — caller is responsible for debouncing)
  const loadMapPoints = useCallback(async (bounds?: MapBounds | null) => {
    const reqId = ++rpcRequestRef.current;
    const params: Record<string, unknown> = { p_limit: MAP_POINTS_LIMIT, p_exclude_solar: !showSolarHomes };
    if (county) params.p_county = county;
    if (city) params.p_city = city;
    if (bounds) {
      params.p_south = bounds.south;
      params.p_north = bounds.north;
      params.p_west = bounds.west;
      params.p_east = bounds.east;
    }
    const { data, error } = await supabaseBrowser.rpc("get_map_points", params).limit(MAP_POINTS_LIMIT);
    if (error) {
      console.error("get_map_points error:", error);
      return;
    }
    // Only apply if this is still the latest request (ignore stale responses)
    if (reqId === rpcRequestRef.current) {
      setRpcMapPoints((data ?? []) as RpcMapPoint[]);
    }
  }, [county, city, showSolarHomes]);

  // Re-fire RPC when filters change (loadMapPoints deps include county/city).
  // Only fire if mapBounds is already set — on initial mount, the debounce
  // effect handles the first load after MapBoundsReporter reports bounds.
  // Without this guard, two concurrent RPCs race and the stale-response
  // rejection discards the first result, leaving the map empty until the
  // debounced call completes.
  useEffect(() => {
    if (mapBounds) loadMapPoints(mapBounds);
  }, [loadMapPoints]);

  useEffect(() => {
    let alive = true;
    async function loadFollows() {
      const { data: userData } = await supabaseBrowser.auth.getUser();
      if (!alive || !userData.user) return;
      setUserId(userData.user.id);
      const { data } = await supabaseBrowser
        .from("user_follows")
        .select("home_index")
        .eq("user_id", userData.user.id);
      if (alive && data) setFollowedHomeIndices(new Set((data as { home_index: string }[]).map((r) => r.home_index)));
      const { data: profile } = await supabaseBrowser
        .from("profiles")
        .select("org_id")
        .eq("user_id", userData.user.id)
        .maybeSingle();
      if (alive && profile?.org_id) setOrgId(profile.org_id as string);
    }
    loadFollows();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    const list = rows ?? [];
    if (list.length === 0 || !orgId) {
      setOrgHomeByIndex({});
      return;
    }
    const indices = list.map((r) => r.index);
    supabaseBrowser
      .from("org_home")
      .select("home_index, tags, interest_in_solar, interest_in_battery, do_not_contact")
      .eq("org_id", orgId)
      .in("home_index", indices)
      .then(({ data }) => {
        if (!alive) return;
        const byIndex: Record<string, { tags: string[]; interest_in_solar: string | null; interest_in_battery: string | null; do_not_contact: boolean }> = {};
        for (const row of (data ?? []) as { home_index: string; tags: string[] | null; interest_in_solar: string | null; interest_in_battery: string | null; do_not_contact: boolean }[]) {
          byIndex[row.home_index] = { tags: row.tags ?? [], interest_in_solar: row.interest_in_solar, interest_in_battery: row.interest_in_battery, do_not_contact: row.do_not_contact ?? false };
        }
        setOrgHomeByIndex(byIndex);
      });
    return () => { alive = false; };
  }, [orgId, rows]);

  const toggleFollow = useCallback(
    async (homeIndex: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!userId) return;
      const isFollowed = followedHomeIndices.has(homeIndex);
      if (isFollowed) {
        await supabaseBrowser.from("user_follows").delete().eq("user_id", userId).eq("home_index", homeIndex);
        setFollowedHomeIndices((prev) => new Set([...prev].filter((x) => x !== homeIndex)));
      } else {
        await supabaseBrowser.from("user_follows").insert({ user_id: userId, home_index: homeIndex });
        setFollowedHomeIndices((prev) => new Set([...prev, homeIndex]));
      }
    },
    [userId, followedHomeIndices]
  );

  useEffect(() => {
    const next = buildHomesSearchParams({
      county,
      city,
      subdivision,
      address: addressSearchApplied || undefined,
      lat: mapCenter?.[0] ?? null,
      lng: mapCenter?.[1] ?? null,
      zoom: mapZoom,
      sortBy,
      minModel: minModelScore,
      minRoof: minRoofScore,
      minSolar: minSolarInterest,
      minBattery: minBatteryInterest,
      tag: tagFilter,
      excludeTag: excludeTagFilter,
      excludeDnc: excludeDoNotContact,
      showSolar: showSolarHomes,
    });
    const nextStr = next.toString();
    const currentStr = typeof window !== "undefined" ? window.location.search.slice(1) : "";
    if (nextStr !== currentStr) {
      router.replace(nextStr ? `${HOMES_PATH}?${nextStr}` : HOMES_PATH, { scroll: false });
    }
  }, [county, city, subdivision, addressSearchApplied, mapCenter, mapZoom, sortBy, minModelScore, minRoofScore, minSolarInterest, minBatteryInterest, tagFilter, excludeTagFilter, excludeDoNotContact, showSolarHomes, router]);

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

  const fetchHomesPage = useCallback(async (opts: {
    bounds?: MapBounds | null;
    pageOffset?: number;
    append?: boolean;
  } = {}) => {
    const { bounds, pageOffset = 0, append = false } = opts;
    if (!append) {
      setErr(null);
      setRows(null);
      setTotalCount(null);
    }
    setBoundsLoading(true);

    const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
    if (userErr) { setErr(userErr.message); setBoundsLoading(false); return; }
    if (!userData.user) { router.push("/login"); setBoundsLoading(false); return; }

    const params: Record<string, unknown> = {
      p_sort_by: sortBy,
      p_show_solar: showSolarHomes,
      p_limit: PAGE_SIZE,
      p_offset: pageOffset,
    };

    if (county) params.p_county = county;
    if (city) params.p_city = city;
    if (subdivision) params.p_subdivision = subdivision;
    if (addressSearchApplied.trim()) params.p_address_search = addressSearchApplied.trim();

    const minModel = parseFloat(minModelScore);
    const minRoof = parseFloat(minRoofScore);
    if (Number.isFinite(minModel)) params.p_min_model = minModel;
    if (Number.isFinite(minRoof)) params.p_min_roof = minRoof;

    if (bounds) {
      params.p_south = bounds.south;
      params.p_north = bounds.north;
      params.p_west = bounds.west;
      params.p_east = bounds.east;
    }

    const { data, error } = await supabaseBrowser.rpc("get_homes_page", params);
    setBoundsLoading(false);

    if (error) { setErr(error.message); setRows([]); return; }

    const results = (data ?? []) as (HomeRow & { total_count: number })[];
    const count = results.length > 0 ? results[0].total_count : 0;

    if (append) {
      setRows(prev => prev ? [...prev, ...results] : results);
    } else {
      setRows(results);
    }
    setTotalCount(count);
    setOffset(pageOffset + PAGE_SIZE);
    setHasMore(results.length === PAGE_SIZE);
  }, [router, county, city, subdivision, addressSearchApplied, sortBy,
      showSolarHomes, minModelScore, minRoofScore]);

  const loadNextPage = useCallback(async () => {
    if (!rows || rows.length === 0) return;
    fetchHomesPage({ bounds: mapBounds, pageOffset: offset, append: true });
  }, [rows?.length, offset, mapBounds, fetchHomesPage]);

  // Initial load (no bounds yet)
  useEffect(() => {
    fetchHomesPage();
  }, [fetchHomesPage]);

  useEffect(() => {
    let alive = true;
    const list = rows ?? [];

    async function signImages() {
      if (!list.length) return;

      const missingRows = list.filter(
        (r) => imgUrls[r.original_index] === undefined && imgErrors[r.original_index] === undefined
      );

      if (missingRows.length === 0) return;

      const results = await Promise.all(
        missingRows.map(async (r) => {
          const path = indexToImagePath(r.index);

          const { data } = supabaseBrowser.storage
            .from(BUCKET)
            .getPublicUrl(path);

          return { oi: r.original_index, url: data?.publicUrl ?? "", errorMsg: "" };
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

  const handleBoundsChange = useCallback((b: MapBounds | null) => {
    setMapBounds(b);
  }, []);

  const handleViewChange = useCallback((center: [number, number], zoom: number) => {
    setMapCenter(center);
    setMapZoom(zoom);
  }, []);

  const boundsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBoundsRef = useRef<MapBounds | null>(null);
  const BOUNDS_EPS = 1e-6;
  function boundsEqual(a: MapBounds, b: MapBounds): boolean {
    return (
      Math.abs(a.north - b.north) < BOUNDS_EPS &&
      Math.abs(a.south - b.south) < BOUNDS_EPS &&
      Math.abs(a.east - b.east) < BOUNDS_EPS &&
      Math.abs(a.west - b.west) < BOUNDS_EPS
    );
  }
  useEffect(() => {
    if (!mapBounds) {
      lastBoundsRef.current = null;
      return;
    }
    if (lastBoundsRef.current && boundsEqual(mapBounds, lastBoundsRef.current)) {
      return;
    }
    const isFirstBounds = lastBoundsRef.current === null;
    lastBoundsRef.current = mapBounds;
    if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
    // Fire immediately on first bounds report (initial load) — no delay
    const delay = isFirstBounds ? 0 : 400;
    boundsDebounceRef.current = setTimeout(() => {
      boundsDebounceRef.current = null;
      loadMapPoints(mapBounds);
      fetchHomesPage({ bounds: mapBounds });
    }, delay);
    return () => {
      if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
    };
  }, [mapBounds, fetchHomesPage, loadMapPoints]);

  const displayedRows = useMemo(() => {
    // Rows are already sorted and score-filtered by the RPC
    let list = rows ?? [];

    // Org-specific filters (client-side, since org_home is fetched separately with RLS)
    const tagLower = tagFilter.trim().toLowerCase();
    const excludeLower = excludeTagFilter.trim().toLowerCase();
    if (tagLower || excludeLower || excludeDoNotContact) {
      list = list.filter((r) => {
        const orgRow = orgHomeByIndex[r.index];
        const tags: string[] = (orgRow?.tags ?? []).map((t) => t.trim().toLowerCase());
        if (tagLower && !tags.some((tag) => tag.startsWith(tagLower))) return false;
        if (excludeLower && tags.some((tag) => tag.startsWith(excludeLower))) return false;
        if (excludeDoNotContact && orgRow?.do_not_contact) return false;
        return true;
      });
    }

    // Interest filters (from org_home real columns)
    if (minSolarInterest && INTEREST_RANK[minSolarInterest]) {
      const minRank = INTEREST_RANK[minSolarInterest];
      list = list.filter((r) => {
        const val = orgHomeByIndex[r.index]?.interest_in_solar ?? "";
        return (INTEREST_RANK[val] ?? 0) >= minRank;
      });
    }
    if (minBatteryInterest && INTEREST_RANK[minBatteryInterest]) {
      const minRank = INTEREST_RANK[minBatteryInterest];
      list = list.filter((r) => {
        const val = orgHomeByIndex[r.index]?.interest_in_battery ?? "";
        return (INTEREST_RANK[val] ?? 0) >= minRank;
      });
    }

    return list;
  }, [rows, tagFilter, excludeTagFilter, excludeDoNotContact, orgHomeByIndex, minSolarInterest, minBatteryInterest]);

  const mapPoints = useMemo(() => {
    const minModel = parseInt(minModelScore, 10);
    const minRoof = parseInt(minRoofScore, 10);

    // Prefer lightweight RPC data for map dots (scores pre-joined, no gray flash)
    if (rpcMapPoints && rpcMapPoints.length > 0) {
      return rpcMapPoints
        .filter((r) => {
          if (!Number.isFinite(r.latitude) || !Number.isFinite(r.longitude)) return false;
          if (Number.isFinite(minModel) && (r.model_score == null || r.model_score < minModel)) return false;
          if (Number.isFinite(minRoof) && (r.roof_score == null || r.roof_score < minRoof)) return false;
          return true;
        })
        .map((r) => {
          let colorScore: number | null = null;
          if (sortBy === "model_score") colorScore = r.model_score;
          else if (sortBy === "roof_score") colorScore = r.roof_score;
          else colorScore = r.hybrid_score;
          return {
            lat: r.latitude,
            lng: r.longitude,
            index: r.index,
            address: r.index, // lightweight — no full address in RPC
            score: colorScore,
            roofScore: r.roof_score,
            modelScore: r.model_score,
          };
        });
    }
    // Fallback: derive from full rows (scores already included from RPC)
    const list = rows ?? [];
    if (!list.length) return [];
    return list
      .filter(
        (r) =>
          r.latitude != null &&
          r.longitude != null &&
          Number.isFinite(Number(r.latitude)) &&
          Number.isFinite(Number(r.longitude))
      )
      .map((r) => {
        const { addressLine1, addressLine2 } = buildListingCardData(r);
        const ms = (r.model_score as number | null) ?? null;
        const rs = (r.roof_score as number | null) ?? null;
        let colorScore: number | null = null;
        if (sortBy === "model_score") colorScore = ms;
        else if (sortBy === "roof_score") colorScore = rs;
        else if (sortBy === "hybrid" && ms != null && rs != null) colorScore = Math.round((ms * 0.6 + rs * 0.4) * 10) / 10;
        else if (sortBy === "hybrid") colorScore = ms ?? rs;
        return {
          lat: Number(r.latitude),
          lng: Number(r.longitude),
          index: r.index,
          address: `${addressLine1}, ${addressLine2}`,
          score: colorScore,
          roofScore: rs,
          modelScore: ms,
        };
      });
  }, [rpcMapPoints, rows, sortBy, minModelScore, minRoofScore]);

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
    setAddressSearchInput("");
    setAddressSearchApplied("");
    setTagFilter("");
    setExcludeTagFilter("");
    setExcludeDoNotContact(true);
    setMinModelScore("");
    setMinRoofScore("");
    setMinSolarInterest("");
    setMinBatteryInterest("");
    setShowSolarHomes(false);
  };

  const hasActiveFilters =
    county ||
    city ||
    subdivision ||
    addressSearchInput.trim() ||
    addressSearchApplied ||
    tagFilter.trim() ||
    excludeTagFilter.trim() ||
    !excludeDoNotContact ||
    minModelScore.trim() ||
    minRoofScore.trim() ||
    minSolarInterest ||
    minBatteryInterest ||
    showSolarHomes;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Explorer
          </h1>
        </header>

        <div className="mb-6 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">Filters</span>
            <span className="group relative">
              <span className="flex h-5 w-5 cursor-default items-center justify-center rounded-full border border-neutral-300 text-xs font-medium text-neutral-400">i</span>
              <span className="pointer-events-none absolute right-0 top-7 z-20 w-56 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs text-slate-600 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                All homes shown are single-family, owner-occupied residential properties.
              </span>
            </span>
          </div>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                <span className="text-xs font-medium text-slate-500">Sort by</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortOption)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  {SORT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
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
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1 sm:w-28">
                <span className="text-xs font-medium text-slate-500">Min ranking score</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={minModelScore}
                  onChange={(e) => setMinModelScore(e.target.value)}
                  placeholder="0"
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>
              <div className="flex flex-col gap-1 sm:w-28">
                <span className="text-xs font-medium text-slate-500">Min roof score</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={minRoofScore}
                  onChange={(e) => setMinRoofScore(e.target.value)}
                  placeholder="0"
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-500">Min solar interest</span>
                <select
                  value={minSolarInterest}
                  onChange={(e) => setMinSolarInterest(e.target.value)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">Any</option>
                  {INTEREST_OPTIONS.filter(Boolean).map((o) => (
                    <option key={o} value={o}>{o}+</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-500">Min battery interest</span>
                <select
                  value={minBatteryInterest}
                  onChange={(e) => setMinBatteryInterest(e.target.value)}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">Any</option>
                  {INTEREST_OPTIONS.filter(Boolean).map((o) => (
                    <option key={o} value={o}>{o}+</option>
                  ))}
                </select>
              </label>
              <div className="flex flex-col gap-1 sm:w-36">
                <span className="text-xs font-medium text-slate-500">Filter by tag</span>
                <input
                  type="text"
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                  placeholder="e.g. hot-lead"
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>
              <div className="flex flex-col gap-1 sm:w-36">
                <span className="text-xs font-medium text-slate-500">Exclude tags</span>
                <input
                  type="text"
                  value={excludeTagFilter}
                  onChange={(e) => setExcludeTagFilter(e.target.value)}
                  placeholder="e.g. not interested"
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>
              <label className="flex cursor-pointer items-center gap-2 self-end py-2">
                <input
                  type="checkbox"
                  checked={excludeDoNotContact}
                  onChange={(e) => setExcludeDoNotContact(e.target.checked)}
                  className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                />
                <span className="text-sm text-slate-600">Exclude do not contact</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2 self-end py-2">
                <input
                  type="checkbox"
                  checked={showSolarHomes}
                  onChange={(e) => setShowSolarHomes(e.target.checked)}
                  className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                />
                <span className="text-sm text-slate-600">Include homes with solar</span>
              </label>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-neutral-400">
              {totalCount != null ? `${totalCount.toLocaleString()} homes match` : ""}
            </span>
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="text-sm font-medium text-slate-600 underline hover:text-slate-900"
              >
                Clear all filters
              </button>
            )}
          </div>
        </div>

        <div className="mb-8">
          <HomeMap
            points={mapPoints}
            initialCenter={initialMapViewRef.current?.center ?? null}
            initialZoom={initialMapViewRef.current?.zoom ?? null}
            onBoundsChange={handleBoundsChange}
            onViewChange={handleViewChange}
          />
        </div>

        <p className="mb-4 text-sm text-slate-600">
          {boundsLoading ? (
            "Loading homes in map view…"
          ) : (
            <>
              Showing {displayedRows.length.toLocaleString()} homes.
              {mapPoints.length >= MAP_POINTS_LIMIT && " Zoom in to see more on map."}
            </>
          )}
        </p>

        <hr className="border-slate-200 mb-4" />
        <p className="mb-6 text-center text-xs text-slate-400 italic">
          Satellite imagery may not match the current condition of the home.
        </p>

        <div className="flex flex-col gap-8">
          {displayedRows.slice(0, offset).map((r) => {
            const url = imgUrls[r.original_index];
            const e = imgErrors[r.original_index];
            const imageUrl = url || "/window.svg";
            const imageAlt = url ? `Home ${r.original_index}` : e ? "No access / not found" : "Loading…";
            const { addressLine1, addressLine2, detailRows } = buildListingCardData(r);
            const tagsArray = (orgHomeByIndex[r.index]?.tags ?? []).filter((t) => t.trim() !== "");
            const cardRows =
              tagsArray.length > 0
                ? [...detailRows, { label: "Tags", value: tagsArray.join(", ") }]
                : detailRows;

            return (
              <Link
                key={r.index}
                href={`/homes/${encodeURIComponent(r.index)}?from=explorer`}
                className="block rounded-2xl text-inherit no-underline"
              >
                <ListingCard
                  addressLine1={addressLine1}
                  addressLine2={addressLine2}
                  imageUrl={imageUrl}
                  imageAlt={imageAlt}
                  rows={cardRows}
                  followState={{
                    isFollowed: followedHomeIndices.has(r.index),
                    onToggle: (e) => toggleFollow(r.index, e),
                  }}
                  unoptimized
                  badge={r.has_solar ? "Has Solar" : undefined}
                />
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}

export default function HomesPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center px-4">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
            <p className="text-slate-600">Loading…</p>
          </div>
        </main>
      }
    >
      <HomesPageContent />
    </Suspense>
  );
}
