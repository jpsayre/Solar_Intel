import Image from "next/image";

type DetailRow = {
  label: string;
  value: string;
};

type ListingCardProps = {
  addressLine1: string;
  addressLine2: string;
  imageUrl: string;
  imageAlt?: string;
  rows: DetailRow[];
  /** When provided, shows a Follow toggle in the top right. */
  followState?: {
    isFollowed: boolean;
    onToggle: (e: React.MouseEvent) => void;
  };
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
  followState,
}: ListingCardProps) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,42%)_1fr]">
        {/* Left: Image */}
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

        {/* Right: Content */}
        <div className="flex flex-col justify-center p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div className="text-xl font-bold tracking-tight text-neutral-800">
                {addressLine1}
              </div>
              <div className="mt-0.5 text-base font-bold tracking-tight text-neutral-800">
                {addressLine2}
              </div>
            </div>
            {followState && (
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-sm font-medium text-slate-700">Follow</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={followState.isFollowed}
                  aria-label={followState.isFollowed ? "Unfollow" : "Follow"}
                  onClick={followState.onToggle}
                  className="focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 rounded-full"
                >
                  <span
                    className={`inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      followState.isFollowed ? "bg-amber-500" : "bg-neutral-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                        followState.isFollowed ? "translate-x-6" : "translate-x-0.5"
                      }`}
                    />
                  </span>
                </button>
              </div>
            )}
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
