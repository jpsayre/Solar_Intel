import { describe, it, expect } from "vitest";

/**
 * Tests for URL search param encoding/decoding.
 * Mirrors buildHomesSearchParams from app/homes/page.tsx.
 */

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
  showSolar?: boolean;
}): URLSearchParams {
  const sp = new URLSearchParams();
  if (params.county?.trim()) sp.set("county", params.county.trim());
  if (params.city?.trim()) sp.set("city", params.city.trim());
  if (params.subdivision?.trim()) sp.set("subdivision", params.subdivision.trim());
  if (params.address?.trim()) sp.set("address", params.address.trim());
  if (params.lat != null && Number.isFinite(params.lat)) sp.set("lat", params.lat.toFixed(5));
  if (params.lng != null && Number.isFinite(params.lng)) sp.set("lng", params.lng.toFixed(5));
  if (params.zoom != null && Number.isFinite(params.zoom)) sp.set("zoom", String(Math.round(params.zoom)));
  if (params.sortBy && params.sortBy !== "hybrid") sp.set("sort", params.sortBy);
  if (params.minModel?.trim()) sp.set("minModel", params.minModel.trim());
  if (params.minRoof?.trim()) sp.set("minRoof", params.minRoof.trim());
  if (params.showSolar) sp.set("solar", "1");
  return sp;
}

describe("buildHomesSearchParams", () => {
  it("preserves lat/lng precision to 5 decimal places", () => {
    const sp = buildHomesSearchParams({ lat: 40.01523, lng: -105.27891 });
    expect(sp.get("lat")).toBe("40.01523");
    expect(sp.get("lng")).toBe("-105.27891");
  });

  it("does NOT round lng to integer", () => {
    const sp = buildHomesSearchParams({ lat: 40.0, lng: -105.27 });
    // This was the bug: Math.round(-105.27) = -105
    expect(sp.get("lng")).not.toBe("-105");
    expect(sp.get("lng")).toBe("-105.27000");
  });

  it("rounds zoom to integer", () => {
    const sp = buildHomesSearchParams({ zoom: 13.7 });
    expect(sp.get("zoom")).toBe("14");
  });

  it("omits hybrid from sort param (it's the default)", () => {
    const sp = buildHomesSearchParams({ sortBy: "hybrid" });
    expect(sp.has("sort")).toBe(false);
  });

  it("includes non-default sort", () => {
    const sp = buildHomesSearchParams({ sortBy: "model_score" });
    expect(sp.get("sort")).toBe("model_score");
  });

  it("omits null/undefined lat/lng", () => {
    const sp = buildHomesSearchParams({ lat: null, lng: null });
    expect(sp.has("lat")).toBe(false);
    expect(sp.has("lng")).toBe(false);
  });

  it("omits empty string filters", () => {
    const sp = buildHomesSearchParams({ county: "", city: "  ", minModel: "" });
    expect(sp.has("county")).toBe(false);
    expect(sp.has("city")).toBe(false);
    expect(sp.has("minModel")).toBe(false);
  });

  it("round-trips lat/lng through parseFloat", () => {
    const original = { lat: 40.01523, lng: -105.27891 };
    const sp = buildHomesSearchParams(original);
    const restored = {
      lat: parseFloat(sp.get("lat")!),
      lng: parseFloat(sp.get("lng")!),
    };
    expect(Math.abs(restored.lat - original.lat)).toBeLessThan(0.00001);
    expect(Math.abs(restored.lng - original.lng)).toBeLessThan(0.00001);
  });

  it("sets solar=1 when showSolar is true", () => {
    const sp = buildHomesSearchParams({ showSolar: true });
    expect(sp.get("solar")).toBe("1");
  });

  it("omits solar param when showSolar is false", () => {
    const sp = buildHomesSearchParams({ showSolar: false });
    expect(sp.has("solar")).toBe(false);
  });
});
