import { describe, it, expect } from "vitest";

/**
 * These tests verify the map point building logic extracted from
 * app/homes/page.tsx. They ensure that MapPoint objects passed to
 * HomeMap always have the correct shape and content.
 *
 * If the map point building logic is refactored into a shared function,
 * import it here. Until then, these test the contract by reimplementing
 * the same logic and asserting the expected output.
 */

type RpcMapPoint = {
  index: string;
  latitude: number;
  longitude: number;
  model_score: number | null;
  roof_score: number | null;
  hybrid_score: number | null;
  address: string | null;
  city: string | null;
  has_solar: boolean | null;
};

type MapPoint = {
  lat: number;
  lng: number;
  index: string;
  address: string;
  score: number | null;
  roofScore: number | null;
  modelScore: number | null;
  hasSolar: boolean;
};

/** Mirrors the logic in app/homes/page.tsx mapPoints useMemo (RPC branch) */
function buildMapPointFromRpc(r: RpcMapPoint, sortBy: string): MapPoint {
  let colorScore: number | null = null;
  if (sortBy === "model_score") colorScore = r.model_score;
  else if (sortBy === "roof_score") colorScore = r.roof_score;
  else colorScore = r.hybrid_score;
  return {
    lat: r.latitude,
    lng: r.longitude,
    index: r.index,
    address: [r.address, r.city].filter(Boolean).join(", ") || r.index,
    score: colorScore,
    roofScore: r.roof_score,
    modelScore: r.model_score,
    hasSolar: r.has_solar ?? false,
  };
}

const sampleRpc: RpcMapPoint = {
  index: "BOULDER_CO_1014",
  latitude: 40.015,
  longitude: -105.27,
  model_score: 85,
  roof_score: 72,
  hybrid_score: 79.8,
  address: "1234 MAIN ST",
  city: "BOULDER",
  has_solar: false,
};

describe("buildMapPointFromRpc", () => {
  it("uses address + city for tooltip, not index", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "hybrid");
    expect(pt.address).toBe("1234 MAIN ST, BOULDER");
    expect(pt.address).not.toBe(pt.index);
  });

  it("falls back to index when address is null", () => {
    const pt = buildMapPointFromRpc({ ...sampleRpc, address: null, city: null }, "hybrid");
    expect(pt.address).toBe("BOULDER_CO_1014");
  });

  it("uses hybrid_score when sortBy is hybrid", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "hybrid");
    expect(pt.score).toBe(79.8);
  });

  it("uses model_score when sortBy is model_score", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "model_score");
    expect(pt.score).toBe(85);
  });

  it("uses roof_score when sortBy is roof_score", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "roof_score");
    expect(pt.score).toBe(72);
  });

  it("passes through roofScore and modelScore separately", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "hybrid");
    expect(pt.roofScore).toBe(72);
    expect(pt.modelScore).toBe(85);
  });

  it("sets hasSolar from RPC data", () => {
    expect(buildMapPointFromRpc(sampleRpc, "hybrid").hasSolar).toBe(false);
    expect(buildMapPointFromRpc({ ...sampleRpc, has_solar: true }, "hybrid").hasSolar).toBe(true);
  });

  it("defaults hasSolar to false when null", () => {
    expect(buildMapPointFromRpc({ ...sampleRpc, has_solar: null }, "hybrid").hasSolar).toBe(false);
  });

  it("maps lat/lng correctly", () => {
    const pt = buildMapPointFromRpc(sampleRpc, "hybrid");
    expect(pt.lat).toBe(40.015);
    expect(pt.lng).toBe(-105.27);
  });
});
