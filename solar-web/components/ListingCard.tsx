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
    <div className="flex items-center justify-between gap-4 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wider text-neutral-500">
        {label.toUpperCase()}
      </div>
      <div className="text-sm font-semibold text-neutral-900">{value}</div>
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
    <section className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,42%)_1fr]">
        {/* Left: Image — full image visible, no crop; column stretches to match content height */}
        <div className="relative aspect-[4/3] w-full overflow-hidden bg-neutral-100 md:aspect-auto md:h-full md:min-h-0 md:rounded-l-2xl">
          <Image
            src={imageUrl}
            alt={imageAlt}
            fill
            sizes="(max-width: 768px) 100vw, 42vw"
            className="object-contain"
            priority={false}
          />
        </div>

        {/* Right: Content — card height follows this so nothing clips */}
        <div className="flex flex-col justify-center p-5">
          <div className="mb-4">
            <div className="text-xl font-bold tracking-tight text-neutral-800">
              {addressLine1}
            </div>
            <div className="mt-0.5 text-base font-bold tracking-tight text-neutral-800">
              {addressLine2}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {rows.map((r, idx) => (
              <PillRow key={`${r.label}-${idx}`} label={r.label} value={r.value} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
