export type CardRow = { label: string; value: string };

type HomeRow = {
  index: string;
  original_index: number;
  owner_1?: string | null;
  owner_2?: string | null;
  address_line_1?: string | null;
  address_1?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  zip_code?: string | null;
  postal_code?: string | null;
  city_state?: string | null;
  address_line_2?: string | null;
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

  const zip = getValue(row, "zip", "zip_code", "postal_code");
  const addressLine1 =
    (row.address_line_1 ?? row.address_1 ?? row.address) != null
      ? String(row.address_line_1 ?? row.address_1 ?? row.address).toUpperCase()
      : row.index;
  const addressLine2 =
    row.city != null && row.state != null
      ? zip !== "—"
        ? `${String(row.city).toUpperCase()}, ${String(row.state).toUpperCase()} ${zip}`
        : `${String(row.city).toUpperCase()}, ${String(row.state).toUpperCase()}`
      : (row.city_state ?? row.address_line_2) != null
        ? zip !== "—"
          ? `${String(row.city_state ?? row.address_line_2).toUpperCase()} ${zip}`
          : String(row.city_state ?? row.address_line_2).toUpperCase()
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
