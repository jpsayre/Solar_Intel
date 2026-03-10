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
  roof?: string[];
  address?: string;
  lat?: number | null;
  lng?: number | null;
  zoom?: number | null;
}): URLSearchParams {
  const sp = new URLSearchParams();
  if (params.county?.trim()) sp.set("county", params.county.trim());
  if (params.city?.trim()) sp.set("city", params.city.trim());
  if (params.subdivision?.trim()) sp.set("subdivision", params.subdivision.trim());
  if (params.roof?.length) sp.set("roof", params.roof.join(","));
  if (params.address?.trim()) sp.set("address", params.address.trim());
  if (params.lat != null && Number.isFinite(params.lat)) sp.set("lat", String(params.lat));
  if (params.lng != null && Number.isFinite(params.lng)) sp.set("lng", String(params.lng));
  if (params.zoom != null && Number.isFinite(params.zoom)) sp.set("zoom", String(Math.round(params.zoom)));
  return sp;
}

const HomeMap = dynamic(() => import("@/components/HomeMap"), { ssr: false });

const BUCKET = "images";
const PAGE_SIZE = 500;
const NEXT_PAGE_SIZE = 100;
const BOUNDS_QUERY_LIMIT = 500;
const FILTER_OPTIONS_LIMIT = 2000;
const MAP_POINTS_LIMIT = 50000;

type HomeRow = {
  index: string;
  original_index: number;
  model_score?: number | null;
  roof_score?: number | null;
  [key: string]: unknown;
};

type SortOption = "model_score" | "roof_score" | "hybrid";
const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "model_score", label: "Ranking score" },
  { value: "roof_score", label: "Roof score" },
  { value: "hybrid", label: "Hybrid" },
];

const ROOF_ORIENTATION_OPTIONS = ["East", "South", "West"] as const;
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
  const [roofOrientations, setRoofOrientations] = useState<string[]>(() => {
    const r = searchParams.get("roof");
    return r ? r.split(",").map((s) => s.trim()).filter(Boolean) : ["East", "South", "West"];
  });
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
  const [boundsRows, setBoundsRows] = useState<HomeRow[]>([]);
  const [boundsLoading, setBoundsLoading] = useState(false);

  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});

  const [sortBy, setSortBy] = useState<SortOption>("hybrid");
  const [scoresByIndex, setScoresByIndex] = useState<Record<string, { model_score: number | null; roof_score: number | null }>>({});
  const [minModelScore, setMinModelScore] = useState("");
  const [minRoofScore, setMinRoofScore] = useState("");
  const [minSolarInterest, setMinSolarInterest] = useState("");
  const [minBatteryInterest, setMinBatteryInterest] = useState("");

  const [followedHomeIndices, setFollowedHomeIndices] = useState<Set<string>>(new Set());
  const [userId, setUserId] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgHomeByIndex, setOrgHomeByIndex] = useState<Record<string, { custom: Record<string, unknown> | null }>>({});
  const [tagFilter, setTagFilter] = useState("");
  const [excludeTagFilter, setExcludeTagFilter] = useState("");
  const [excludeDoNotContact, setExcludeDoNotContact] = useState(true);

  // Lightweight map points from RPC (scores pre-joined, no gray flash)
  type RpcMapPoint = { index: string; latitude: number; longitude: number; model_score: number | null; roof_score: number | null; hybrid_score: number | null };
  const [rpcMapPoints, setRpcMapPoints] = useState<RpcMapPoint[] | null>(null);

  useEffect(() => {
    let alive = true;
    async function loadMapPoints() {
      const { data: userData } = await supabaseBrowser.auth.getUser();
      if (!alive || !userData.user) return;
      const params: Record<string, unknown> = { p_limit: MAP_POINTS_LIMIT };
      if (county) params.p_county = county;
      if (city) params.p_city = city;
      const { data, error } = await supabaseBrowser.rpc("get_map_points", params);
      if (!alive) return;
      if (error) {
        console.error("get_map_points error:", error);
        return;
      }
      setRpcMapPoints((data ?? []) as RpcMapPoint[]);
    }
    loadMapPoints();
    return () => { alive = false; };
  }, [county, city]);

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

  // Fetch home_scores for current rows
  useEffect(() => {
    let alive = true;
    const list = mapBounds ? boundsRows : (rows ?? []);
    if (list.length === 0) return;
    const indices = list.map((r) => r.index);
    supabaseBrowser
      .from("home_scores")
      .select("home_index, model_score, roof_score")
      .in("home_index", indices)
      .then(({ data }) => {
        if (!alive) return;
        const byIndex: Record<string, { model_score: number | null; roof_score: number | null }> = {};
        for (const row of (data ?? []) as { home_index: string; model_score: number | null; roof_score: number | null }[]) {
          byIndex[row.home_index] = { model_score: row.model_score, roof_score: row.roof_score };
        }
        setScoresByIndex(byIndex);
      });
    return () => { alive = false; };
  }, [mapBounds, boundsRows, rows]);

  useEffect(() => {
    let alive = true;
    const list = mapBounds ? boundsRows : (rows ?? []);
    if (list.length === 0 || !orgId) {
      setOrgHomeByIndex({});
      return;
    }
    const indices = list.map((r) => r.index);
    supabaseBrowser
      .from("org_home")
      .select("home_index, custom")
      .eq("org_id", orgId)
      .in("home_index", indices)
      .then(({ data }) => {
        if (!alive) return;
        const byIndex: Record<string, { custom: Record<string, unknown> | null }> = {};
        for (const row of (data ?? []) as { home_index: string; custom: Record<string, unknown> | null }[]) {
          byIndex[row.home_index] = { custom: row.custom ?? null };
        }
        setOrgHomeByIndex(byIndex);
      });
    return () => { alive = false; };
  }, [orgId, mapBounds, boundsRows, rows]);

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
      roof: roofOrientations.length ? roofOrientations : undefined,
      address: addressSearchApplied || undefined,
      lat: mapCenter?.[0] ?? null,
      lng: mapCenter?.[1] ?? null,
      zoom: mapZoom,
    });
    const nextStr = next.toString();
    const currentStr = typeof window !== "undefined" ? window.location.search.slice(1) : "";
    if (nextStr !== currentStr) {
      router.replace(nextStr ? `${HOMES_PATH}?${nextStr}` : HOMES_PATH, { scroll: false });
    }
  }, [county, city, subdivision, roofOrientations, addressSearchApplied, mapCenter, mapZoom, router]);

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

    const list = (data ?? []) as HomeRow[];
    setRows(list);
    setOffset(PAGE_SIZE);
    setHasMore(list.length === PAGE_SIZE);
    setMapBounds(null);
    setBoundsRows([]);
  }, [router, county, city, subdivision, roofOrientations, addressSearchApplied]);

  const loadNextPage = useCallback(async () => {
    if (!rows || rows.length === 0) return;
    const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
    if (userErr || !userData.user) return;

    let query = supabaseBrowser
      .from("homes")
      .select("*")
      .order("index", { ascending: true })
      .range(offset, offset + NEXT_PAGE_SIZE - 1);

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
    if (error) return;
    const next = (data ?? []) as HomeRow[];
    setRows((prev) => (prev ? [...prev, ...next] : next));
    setOffset((prev) => prev + NEXT_PAGE_SIZE);
    setHasMore(next.length === NEXT_PAGE_SIZE);
  }, [rows?.length, offset, county, city, subdivision, roofOrientations, addressSearchApplied]);

  useEffect(() => {
    let alive = true;
    loadRows();
    return () => {
      alive = false;
    };
  }, [loadRows]);

  const loadRowsInBounds = useCallback(
    async (bounds: MapBounds) => {
      setBoundsLoading(true);
      const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
      if (userErr || !userData.user) {
        setBoundsLoading(false);
        return;
      }

      let query = supabaseBrowser
        .from("homes")
        .select("*")
        .order("index", { ascending: true })
        .gte("latitude", bounds.south)
        .lte("latitude", bounds.north)
        .gte("longitude", bounds.west)
        .lte("longitude", bounds.east)
        .limit(BOUNDS_QUERY_LIMIT);

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
      setBoundsLoading(false);
      if (!error && data) setBoundsRows((data ?? []) as HomeRow[]);
    },
    [county, city, subdivision, roofOrientations, addressSearchApplied]
  );

  useEffect(() => {
    let alive = true;
    const list = mapBounds ? boundsRows : (rows ?? []);

    async function signImages() {
      if (!list.length) return;

      const missingRows = list.filter(
        (r) => imgUrls[r.original_index] === undefined && imgErrors[r.original_index] === undefined
      );

      if (missingRows.length === 0) return;

      const results = await Promise.all(
        missingRows.map(async (r) => {
          const path = indexToImagePath(r.index);

          const { data, error } = await supabaseBrowser.storage
            .from(BUCKET)
            .createSignedUrl(path, 60 * 30); // 30 minutes

          if (error) {
            console.error("SIGNED URL ERROR (list)", { bucket: BUCKET, path, error });
            return { oi: r.original_index, url: "", errorMsg: error.message ?? "storage error" };
          }

          return { oi: r.original_index, url: data?.signedUrl ?? "", errorMsg: "" };
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
  }, [rows, mapBounds, boundsRows, imgUrls, imgErrors]);

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
      setBoundsRows([]);
      return;
    }
    if (lastBoundsRef.current && boundsEqual(mapBounds, lastBoundsRef.current)) {
      return;
    }
    lastBoundsRef.current = mapBounds;
    if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
    boundsDebounceRef.current = setTimeout(() => {
      boundsDebounceRef.current = null;
      loadRowsInBounds(mapBounds);
    }, 400);
    return () => {
      if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
    };
  }, [mapBounds, loadRowsInBounds]);

  const displayedRows = useMemo(() => {
    let list = mapBounds ? boundsRows : (rows ?? []);

    // Merge scores onto rows
    list = list.map((r) => {
      const scores = scoresByIndex[r.index];
      if (!scores) return r;
      return { ...r, model_score: scores.model_score, roof_score: scores.roof_score };
    });

    const tagLower = tagFilter.trim().toLowerCase();
    const excludeLower = excludeTagFilter.trim().toLowerCase();
    if (tagLower || excludeLower || excludeDoNotContact) {
      list = list.filter((r) => {
        const custom = orgHomeByIndex[r.index]?.custom;
        const tags: string[] = custom && typeof custom === "object" && Array.isArray(custom.tags)
          ? (custom.tags as unknown[]).filter((t): t is string => typeof t === "string").map((t) => t.trim().toLowerCase())
          : [];
        if (tagLower && !tags.some((tag) => tag.startsWith(tagLower))) return false;
        if (excludeLower && tags.some((tag) => tag.startsWith(excludeLower))) return false;
        if (excludeDoNotContact && tags.some((tag) => tag.startsWith("do not contact"))) return false;
        return true;
      });
    }

    // Score minimum filters
    const minModel = parseInt(minModelScore, 10);
    const minRoof = parseInt(minRoofScore, 10);
    if (Number.isFinite(minModel)) {
      list = list.filter((r) => (r.model_score as number | null | undefined) != null && (r.model_score as number) >= minModel);
    }
    if (Number.isFinite(minRoof)) {
      list = list.filter((r) => (r.roof_score as number | null | undefined) != null && (r.roof_score as number) >= minRoof);
    }

    // Interest filters (from org_home custom data)
    if (minSolarInterest && INTEREST_RANK[minSolarInterest]) {
      const minRank = INTEREST_RANK[minSolarInterest];
      list = list.filter((r) => {
        const custom = orgHomeByIndex[r.index]?.custom;
        const val = custom && typeof custom === "object" ? (custom.interest_in_solar as string) : "";
        return (INTEREST_RANK[val] ?? 0) >= minRank;
      });
    }
    if (minBatteryInterest && INTEREST_RANK[minBatteryInterest]) {
      const minRank = INTEREST_RANK[minBatteryInterest];
      list = list.filter((r) => {
        const custom = orgHomeByIndex[r.index]?.custom;
        const val = custom && typeof custom === "object" ? (custom.interest_in_battery as string) : "";
        return (INTEREST_RANK[val] ?? 0) >= minRank;
      });
    }

    // Sort
    list = [...list].sort((a, b) => {
      if (sortBy === "model_score") {
        const sa = (a.model_score as number | null | undefined) ?? -1;
        const sb = (b.model_score as number | null | undefined) ?? -1;
        return sb - sa;
      }
      if (sortBy === "roof_score") {
        const sa = (a.roof_score as number | null | undefined) ?? -1;
        const sb = (b.roof_score as number | null | undefined) ?? -1;
        return sb - sa;
      }
      // hybrid: 0.6 * ranking + 0.4 * roof
      const ha = ((a.model_score as number | null | undefined) ?? 0) * 0.6 + ((a.roof_score as number | null | undefined) ?? 0) * 0.4;
      const hb = ((b.model_score as number | null | undefined) ?? 0) * 0.6 + ((b.roof_score as number | null | undefined) ?? 0) * 0.4;
      return hb - ha;
    });

    return list;
  }, [mapBounds, boundsRows, rows, tagFilter, excludeTagFilter, excludeDoNotContact, orgHomeByIndex, scoresByIndex, sortBy, minModelScore, minRoofScore, minSolarInterest, minBatteryInterest]);

  const mapPoints = useMemo(() => {
    // Prefer lightweight RPC data for map dots (scores pre-joined, no gray flash)
    if (rpcMapPoints && rpcMapPoints.length > 0) {
      return rpcMapPoints
        .filter((r) => Number.isFinite(r.latitude) && Number.isFinite(r.longitude))
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
          };
        });
    }
    // Fallback: derive from full rows + separate scores (legacy path)
    const list = mapBounds ? boundsRows : (rows ?? []);
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
        const scores = scoresByIndex[r.index];
        const ms = scores?.model_score ?? null;
        const rs = scores?.roof_score ?? null;
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
        };
      });
  }, [rpcMapPoints, rows, mapBounds, boundsRows, scoresByIndex, sortBy]);

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
    setRoofOrientations(["East", "South", "West"]);
    setAddressSearchInput("");
    setAddressSearchApplied("");
    setTagFilter("");
    setExcludeTagFilter("");
    setExcludeDoNotContact(true);
    setMinModelScore("");
    setMinRoofScore("");
    setMinSolarInterest("");
    setMinBatteryInterest("");
  };

  const toggleRoofOrientation = (orientation: string) => {
    setRoofOrientations((prev) =>
      prev.includes(orientation) ? prev.filter((o) => o !== orientation) : [...prev, orientation]
    );
  };

  const roofOrientationDefault = ["East", "South", "West"];
  const roofIsDefault =
    roofOrientations.length === roofOrientationDefault.length &&
    roofOrientationDefault.every((o) => roofOrientations.includes(o));

  const hasActiveFilters =
    county ||
    city ||
    subdivision ||
    (roofOrientations.length > 0 && !roofIsDefault) ||
    addressSearchInput.trim() ||
    addressSearchApplied ||
    tagFilter.trim() ||
    excludeTagFilter.trim() ||
    !excludeDoNotContact ||
    minModelScore.trim() ||
    minRoofScore.trim() ||
    minSolarInterest ||
    minBatteryInterest;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Explorer
          </h1>
        </header>

        <div className="mb-6 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-3 text-sm font-semibold text-slate-700">Filters</div>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
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

        <div className="mb-8">
          <HomeMap
            points={mapPoints}
            initialCenter={initialMapViewRef.current?.center ?? null}
            initialZoom={initialMapViewRef.current?.zoom ?? null}
            onBoundsChange={handleBoundsChange}
            onViewChange={handleViewChange}
          />
        </div>

        {mapBounds != null && (
          <p className="mb-4 text-sm text-slate-600">
            {boundsLoading ? (
              "Loading homes in map view…"
            ) : (
              <>
                Showing {displayedRows.length} homes in map view.{" "}
                <button
                  type="button"
                  onClick={() => setMapBounds(null)}
                  className="font-medium text-amber-600 underline hover:text-amber-700"
                >
                  Show all
                </button>
              </>
            )}
          </p>
        )}

        {!mapBounds && hasMore && (
          <div className="mb-6">
            <button
              type="button"
              onClick={() => loadNextPage()}
              className="rounded-xl border border-neutral-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Next — load 100 more
            </button>
          </div>
        )}

        <div className="flex flex-col gap-8">
          {displayedRows.map((r) => {
            const url = imgUrls[r.original_index];
            const e = imgErrors[r.original_index];
            const imageUrl = url || "/window.svg";
            const imageAlt = url ? `Home ${r.original_index}` : e ? "No access / not found" : "Loading…";
            const { addressLine1, addressLine2, detailRows } = buildListingCardData(r);
            const orgCustom = orgHomeByIndex[r.index]?.custom;
            const tagsArray =
              orgCustom && typeof orgCustom === "object" && Array.isArray(orgCustom.tags)
                ? (orgCustom.tags as unknown[]).filter((t): t is string => typeof t === "string" && t.trim() !== "").map((t) => t.trim())
                : [];
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
