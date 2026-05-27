import { describe, it, expect } from "vitest";
import { buildListingCardData, buildFollowingCardRows } from "../lib/cardData";

// ---------------------------------------------------------------------------
// buildListingCardData
// ---------------------------------------------------------------------------
describe("buildListingCardData", () => {
  const baseRow = {
    index: "BOULDER_CO_1014",
    original_index: 1014,
    owner_1: "SMITH JOHN",
    owner_2: "SMITH JANE",
    address: "1234 Main St",
    city: "Boulder",
    state: "CO",
    zip_code: "80301",
    saleprice: 500000,
    saledate: "2023-06-15",
    calculated_build_year: 1998,
    building_sqft: 2400,
    model_score: 85.3,
    roof_score: 72.1,
  };

  it("returns uppercase address in addressLine1", () => {
    const { addressLine1 } = buildListingCardData(baseRow);
    expect(addressLine1).toBe("1234 MAIN ST");
  });

  it("falls back to index when address is null", () => {
    const { addressLine1 } = buildListingCardData({ ...baseRow, address: null });
    expect(addressLine1).toBe("BOULDER_CO_1014");
  });

  it("formats addressLine2 as CITY, STATE ZIP", () => {
    const { addressLine2 } = buildListingCardData(baseRow);
    expect(addressLine2).toBe("BOULDER, CO 80301");
  });

  it("falls back to ID when city/state are null", () => {
    const { addressLine2 } = buildListingCardData({ ...baseRow, city: null, state: null });
    expect(addressLine2).toBe("ID: 1014");
  });

  it("shows both owners joined with &", () => {
    const { detailRows } = buildListingCardData(baseRow);
    const owner = detailRows.find((r) => r.label === "Owner name");
    expect(owner?.value).toBe("SMITH JOHN & SMITH JANE");
  });

  it("shows single owner when owner_2 is null", () => {
    const { detailRows } = buildListingCardData({ ...baseRow, owner_2: null });
    const owner = detailRows.find((r) => r.label === "Owner name");
    expect(owner?.value).toBe("SMITH JOHN");
  });

  it("shows fallback when both owners null", () => {
    const { detailRows } = buildListingCardData({ ...baseRow, owner_1: null, owner_2: null });
    const owner = detailRows.find((r) => r.label === "Owner name");
    expect(owner?.value).toBe("Available in full report");
  });

  it("formats sale price with $ and commas", () => {
    const { detailRows } = buildListingCardData(baseRow);
    const price = detailRows.find((r) => r.label === "Sale price");
    expect(price?.value).toBe("$500,000");
  });

  it("shows — for null sale price", () => {
    const { detailRows } = buildListingCardData({ ...baseRow, saleprice: null });
    const price = detailRows.find((r) => r.label === "Sale price");
    expect(price?.value).toBe("—");
  });

  it("shows model_score as ranking score", () => {
    const { detailRows } = buildListingCardData(baseRow);
    const score = detailRows.find((r) => r.label === "Ranking score");
    expect(score?.value).toBe("85.3");
  });

  it("shows — for null model_score", () => {
    const { detailRows } = buildListingCardData({ ...baseRow, model_score: null });
    const score = detailRows.find((r) => r.label === "Ranking score");
    expect(score?.value).toBe("—");
  });

  it("shows roof_score", () => {
    const { detailRows } = buildListingCardData(baseRow);
    const score = detailRows.find((r) => r.label === "Roof score");
    expect(score?.value).toBe("72.1");
  });

  it("returns exactly 7 detail rows in correct order", () => {
    const { detailRows } = buildListingCardData(baseRow);
    expect(detailRows).toHaveLength(7);
    expect(detailRows.map((r) => r.label)).toEqual([
      "Ranking score",
      "Roof score",
      "Owner name",
      "Sale price",
      "Sale date",
      "Build year",
      "Square footage",
    ]);
  });

  it("formats square footage with commas", () => {
    const { detailRows } = buildListingCardData({ ...baseRow, building_sqft: 12500 });
    const sqft = detailRows.find((r) => r.label === "Square footage");
    expect(sqft?.value).toBe("12,500");
  });

  it("formats sale date as MM/DD/YYYY", () => {
    const { detailRows } = buildListingCardData(baseRow);
    const date = detailRows.find((r) => r.label === "Sale date");
    expect(date?.value).toMatch(/^\d{2}\/\d{2}\/\d{4}$/);
  });
});

// ---------------------------------------------------------------------------
// buildFollowingCardRows
// ---------------------------------------------------------------------------
describe("buildFollowingCardRows", () => {
  const homeRow = {
    index: "BOULDER_CO_1014",
    original_index: 1014,
    owner_1: "SMITH JOHN",
    owner_2: null,
  };

  it("shows owner name", () => {
    const rows = buildFollowingCardRows(homeRow, null, null);
    const owner = rows.find((r) => r.label === "Owner name");
    expect(owner?.value).toBe("SMITH JOHN");
  });

  it("shows contact info when contacts provided", () => {
    const rows = buildFollowingCardRows(
      homeRow,
      { contacts: [{ preferred_name: "John", phone_number: "555-1234", email: "john@test.com" }] },
      null,
    );
    const contact = rows.find((r) => r.label === "Contact info");
    expect(contact?.value).toContain("John");
    expect(contact?.value).toContain("555-1234");
    expect(contact?.value).toContain("john@test.com");
    expect(contact?.selectable).toBe(true);
  });

  it("shows fallback when no contacts", () => {
    const rows = buildFollowingCardRows(homeRow, null, null);
    const contact = rows.find((r) => r.label === "Contact info");
    expect(contact?.value).toBe("No contact information for home");
  });

  it("shows open action items as list", () => {
    const rows = buildFollowingCardRows(
      homeRow,
      { actionItems: [{ body: "Call homeowner", completed: false }, { body: "Done task", completed: true }] },
      null,
    );
    const items = rows.find((r) => r.label === "Open action items");
    expect(items?.value).toBe("Call homeowner");
    expect(items?.listStyle).toBe(true);
  });

  it("shows latest comment", () => {
    const rows = buildFollowingCardRows(homeRow, null, { body: "Spoke with owner" });
    const comment = rows.find((r) => r.label === "Most recent comment");
    expect(comment?.value).toBe("Spoke with owner");
  });

  it("shows tags when provided", () => {
    const rows = buildFollowingCardRows(homeRow, { tags: ["hot-lead", "callback"] }, null);
    const tags = rows.find((r) => r.label === "Tags");
    expect(tags?.value).toBe("hot-lead, callback");
  });

  it("omits tags row when no tags", () => {
    const rows = buildFollowingCardRows(homeRow, { tags: [] }, null);
    const tags = rows.find((r) => r.label === "Tags");
    expect(tags).toBeUndefined();
  });
});
