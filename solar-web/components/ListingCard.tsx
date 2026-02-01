import Image from "next/image";

type DetailRow = {
  label: string;
  value: string;
};

type ListingCardProps = {
  addressLine1: string; // e.g. "2279 PICADILLY CIR"
  addressLine2: string; // e.g. "LONGMONT, CO"
  imageUrl: string;
  imageAlt?: string;
  rows: DetailRow[];
};

function PillRow({ label, value }: DetailRow) {
  return (
    <div className="flex items-center justify-between gap-6 rounded-2xl border border-neutral-200 bg-white px-5 py-4">
      <div className="text-xs font-semibold tracking-widest text-neutral-500">
        {label.toUpperCase()}
      </div>
      <div className="text-sm font-medium text-neutral-900">{value}</div>
    </div>
  );
}

export default function ListingCard({
  addressLine1,
  addressLine2,
  imageUrl,
  imageAlt = "",
  rows,
}: ListingCardProps) {
  return (
    <section className="rounded-3xl border border-neutral-200 bg-white shadow-sm">
      <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-[420px_1fr]">
        {/* Left: Image */}
        <div className="relative overflow-hidden rounded-2xl bg-neutral-100">
          {/* Keep a consistent aspect ratio like the prototype */}
          <div className="relative aspect-[4/3] w-full">
            <Image
              src={imageUrl}
              alt={imageAlt}
              fill
              sizes="(max-width: 768px) 100vw, 420px"
              className="object-cover"
              priority={false}
            />
          </div>
        </div>

        {/* Right: Content */}
        <div className="flex flex-col">
          {/* Address header */}
          <div className="mb-4">
            <div className="text-2xl font-extrabold tracking-tight text-neutral-900">
              {addressLine1}
            </div>
            <div className="text-lg font-extrabold tracking-tight text-neutral-900">
              {addressLine2}
            </div>
          </div>

          {/* Rows */}
          <div className="flex flex-col gap-4">
            {rows.map((r, idx) => (
              <PillRow key={`${r.label}-${idx}`} label={r.label} value={r.value} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
