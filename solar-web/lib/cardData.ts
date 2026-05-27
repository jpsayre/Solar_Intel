export type CardRow = { label: string; value: string; selectable?: boolean; listStyle?: boolean; disclaimer?: string };

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
  model_score?: number | null;
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
  // Owner name hidden in public mode. Restore when login is re-enabled.
  // const ownerName =
  //   row.owner_1 != null && String(row.owner_1).trim() !== ""
  //     ? row.owner_2 != null && String(row.owner_2).trim() !== ""
  //       ? `${row.owner_1} & ${row.owner_2}`
  //       : String(row.owner_1)
  //     : "Available in full report";

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

  const modelScore = row.has_solar ? "N/A" : row.model_score != null ? String(row.model_score) : "—";

  const detailRows: CardRow[] = [
    { label: "Ranking score", value: modelScore },
    // { label: "Owner name", value: ownerName },
    { label: "Sale price", value: formatSalePrice(row.saleprice) },
    { label: "Sale date", value: formatDateMMDDYYYY(row.saledate) },
    { label: "Build year", value: getValue(row, "calculated_build_year") },
    { label: "Square footage", value: formatNumberWithCommas(row.building_sqft) },
  ];

  return { addressLine1, addressLine2, detailRows };
}

type FollowingContact = {
  preferred_name?: string | null;
  phone_number?: string | null;
  email?: string | null;
};

type FollowingActionItem = {
  body?: string | null;
  completed?: boolean;
};

/** Build detail rows for the Following page. */
export function buildFollowingCardRows(
  _homeRow: HomeRow,
  orgData: {
    contacts?: FollowingContact[];
    actionItems?: FollowingActionItem[];
    tags?: string[];
  } | null | undefined,
  latestNote: { body: string } | null | undefined,
): CardRow[] {
  // Owner name hidden in public mode. Restore when login is re-enabled.
  // const ownerName =
  //   homeRow.owner_1 != null && String(homeRow.owner_1).trim() !== ""
  //     ? homeRow.owner_2 != null && String(homeRow.owner_2).trim() !== ""
  //       ? `${homeRow.owner_1} & ${homeRow.owner_2}`
  //       : String(homeRow.owner_1)
  //     : "—";

  let contactValue = "No contact information for home";
  if (orgData?.contacts && orgData.contacts.length > 0) {
    const parts: string[] = [];
    for (const c of orgData.contacts) {
      const name = (c.preferred_name ?? "").trim();
      const phone = (c.phone_number ?? "").trim();
      const email = (c.email ?? "").trim();
      if (name || phone || email) {
        parts.push([name, phone, email].filter(Boolean).join(" • "));
      }
    }
    if (parts.length > 0) contactValue = parts.join("\n");
  }

  let actionItemsValue = "No open action items";
  if (orgData?.actionItems) {
    const open = orgData.actionItems.filter((a) => !a.completed && (a.body ?? "").trim() !== "");
    if (open.length > 0) {
      actionItemsValue = open.map((a) => (a.body ?? "").trim()).join("\n");
    }
  }

  const latestCommentValue =
    latestNote && typeof latestNote.body === "string" && latestNote.body.trim() !== ""
      ? latestNote.body.trim()
      : "No comments yet";

  const tagsValue = orgData?.tags && orgData.tags.length > 0
    ? orgData.tags.join(", ")
    : "—";

  const rows: CardRow[] = [
    // { label: "Owner name", value: ownerName },
    { label: "Contact info", value: contactValue, selectable: true },
    { label: "Open action items", value: actionItemsValue, listStyle: actionItemsValue !== "No open action items" },
    { label: "Most recent comment", value: latestCommentValue },
  ];
  if (tagsValue !== "—") {
    rows.push({ label: "Tags", value: tagsValue });
  }
  return rows;
}
