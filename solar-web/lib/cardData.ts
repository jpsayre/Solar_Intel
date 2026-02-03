export type CardRow = { label: string; value: string; selectable?: boolean; listStyle?: boolean };

/** Matches Supabase public.homes table (+ optional extras). */
type HomeRow = {
  index: string;
  original_index: number;
  owner_1?: string | null;
  owner_2?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  zip_code?: number | string | null;
  subdivision_formatted?: string | null;
  qualified_orientations?: string | null;
  saleprice?: number | string | null;
  saledate?: string | null;
  calculated_build_year?: number | string | null;
  building_sqft?: number | string | null;
  [key: string]: unknown;
};

function getValue(row: HomeRow, ...keys: string[]): string {
  for (const key of keys) {
    const v = row[key];
    if (v != null && String(v).trim() !== "") return String(v);
  }
  return "—";
}

function formatDateMMDDYYYY(raw: unknown): string {
  if (raw == null || String(raw).trim() === "") return "—";
  const s = String(raw).trim();
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const year = d.getFullYear();
  return `${month}/${day}/${year}`;
}

function formatNumberWithCommas(raw: unknown): string {
  if (raw == null || String(raw).trim() === "") return "—";
  const n = Number(String(raw).replace(/,/g, ""));
  if (Number.isNaN(n)) return String(raw);
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatSalePrice(raw: unknown): string {
  const formatted = formatNumberWithCommas(raw);
  return formatted === "—" ? "—" : `$${formatted}`;
}

export function buildListingCardData(row: HomeRow): {
  addressLine1: string;
  addressLine2: string;
  detailRows: CardRow[];
} {
  const ownerName =
    row.owner_1 != null && String(row.owner_1).trim() !== ""
      ? row.owner_2 != null && String(row.owner_2).trim() !== ""
        ? `${row.owner_1} & ${row.owner_2}`
        : String(row.owner_1)
      : "Available in full report";

  const zipRaw = row.zip_code != null ? String(Math.floor(Number(row.zip_code))) : "";
  const zip = zipRaw !== "" && !Number.isNaN(Number(zipRaw)) ? zipRaw : "—";
  const addressLine1 =
    row.address != null && String(row.address).trim() !== ""
      ? String(row.address).toUpperCase()
      : row.index;
  const addressLine2 =
    row.city != null && row.state != null
      ? zip !== "—"
        ? `${String(row.city).toUpperCase()}, ${String(row.state).toUpperCase()} ${zip}`
        : `${String(row.city).toUpperCase()}, ${String(row.state).toUpperCase()}`
      : `ID: ${row.original_index}`;

  const detailRows: CardRow[] = [
    { label: "Owner name", value: ownerName },
    { label: "Orientation", value: getValue(row, "qualified_orientations") },
    { label: "Sale price", value: formatSalePrice(row.saleprice) },
    { label: "Sale date", value: formatDateMMDDYYYY(row.saledate) },
    { label: "Build year", value: getValue(row, "calculated_build_year") },
    { label: "Square footage", value: formatNumberWithCommas(row.building_sqft) },
  ];

  return { addressLine1, addressLine2, detailRows };
}

/** Contact shape stored in org_home.custom.contacts */
type ContactEntry = {
  phone_number?: string;
  email?: string;
  preferred_name?: string;
};

/** Action item shape in org_home.custom.action_items */
type ActionItemEntry = {
  id?: string;
  text?: string;
  completed?: boolean;
  created_at?: string;
};

/** Build detail rows for the Following page: owner, contact info, open action items, latest comment. */
export function buildFollowingCardRows(
  homeRow: HomeRow,
  orgCustom: Record<string, unknown> | null | undefined,
  latestNote: { body: string } | null | undefined
): CardRow[] {
  const ownerName =
    homeRow.owner_1 != null && String(homeRow.owner_1).trim() !== ""
      ? homeRow.owner_2 != null && String(homeRow.owner_2).trim() !== ""
        ? `${homeRow.owner_1} & ${homeRow.owner_2}`
        : String(homeRow.owner_1)
      : "—";

  let contactValue = "No contact information for home";
  if (orgCustom && typeof orgCustom === "object" && Array.isArray(orgCustom.contacts)) {
    const contacts = orgCustom.contacts as ContactEntry[];
    const parts: string[] = [];
    for (const c of contacts) {
      if (!c || typeof c !== "object") continue;
      const name = typeof c.preferred_name === "string" ? c.preferred_name.trim() : "";
      const phone = typeof c.phone_number === "string" ? c.phone_number.trim() : "";
      const email = typeof c.email === "string" ? c.email.trim() : "";
      if (name || phone || email) {
        parts.push([name, phone, email].filter(Boolean).join(" • "));
      }
    }
    if (parts.length > 0) contactValue = parts.join("\n");
  }

  let actionItemsValue = "No open action items";
  if (orgCustom && typeof orgCustom === "object" && Array.isArray(orgCustom.action_items)) {
    const items = (orgCustom.action_items as ActionItemEntry[]).filter(
      (a): a is ActionItemEntry => a != null && typeof a === "object" && !a.completed && String(a.text ?? "").trim() !== ""
    );
    if (items.length > 0) {
      actionItemsValue = items.map((a) => String(a.text).trim()).join("\n");
    }
  }

  const latestCommentValue =
    latestNote && typeof latestNote.body === "string" && latestNote.body.trim() !== ""
      ? latestNote.body.trim()
      : "No comments yet";

  let tagsValue = "—";
  if (orgCustom && typeof orgCustom === "object" && Array.isArray(orgCustom.tags)) {
    const tagStrings = (orgCustom.tags as unknown[]).filter((t): t is string => typeof t === "string" && t.trim() !== "").map((t) => t.trim());
    if (tagStrings.length > 0) tagsValue = tagStrings.join(", ");
  }

  const rows: CardRow[] = [
    { label: "Owner name", value: ownerName },
    { label: "Contact info", value: contactValue, selectable: true },
    { label: "Open action items", value: actionItemsValue, listStyle: actionItemsValue !== "No open action items" },
    { label: "Most recent comment", value: latestCommentValue },
  ];
  if (tagsValue !== "—") {
    rows.push({ label: "Tags", value: tagsValue });
  }
  return rows;
}
