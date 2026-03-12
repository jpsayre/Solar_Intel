import Image from "next/image";

type DetailRow = {
  label: string;
  value: string;
  selectable?: boolean;
  listStyle?: boolean;
  disclaimer?: string;
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
  /** When true, row label is above value (taller). When false, label and value are side-by-side (compact). Default false. */
  stackedRows?: boolean;
  /** Preload and don't lazy-load (use for above-the-fold hero images). */
  priority?: boolean;
  /** Skip Vercel image optimization; load directly from URL (saves transformations, good for single-image pages). */
  unoptimized?: boolean;
  /** Optional badge text shown in the top-left corner of the card. */
  badge?: string;
  /** When provided, shows a "Report an issue" link at the bottom. */
  onReportIssue?: (e: React.MouseEvent) => void;
};

function PillRow({
  label,
  value,
  selectable,
  listStyle,
  disclaimer,
  stacked,
}: DetailRow & { stacked?: boolean }) {
  const valueContent = listStyle ? (
    <ul className="list-disc list-outside pl-5 text-sm font-semibold text-neutral-900 min-w-0 space-y-1">
      {value
        .split("\n")
        .filter((line) => line.trim() !== "")
        .map((line, i) => (
          <li key={i}>{line.trim()}</li>
        ))}
    </ul>
  ) : (
    <div
      className={`text-sm font-semibold text-neutral-900 min-w-0 whitespace-pre-line ${selectable ? "cursor-text select-text" : ""}`}
      {...(selectable && {
        onPointerDown: (e: React.PointerEvent) => e.stopPropagation(),
        onPointerUp: (e: React.PointerEvent) => e.stopPropagation(),
        onMouseDown: (e: React.MouseEvent) => e.stopPropagation(),
        onMouseUp: (e: React.MouseEvent) => e.stopPropagation(),
        onClick: (e: React.MouseEvent) => {
          e.stopPropagation();
          e.preventDefault();
        },
      })}
    >
      {value}
    </div>
  );

  if (stacked) {
    return (
      <div className="flex flex-col gap-1.5 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3">
        <div className="text-xs font-medium uppercase tracking-wider text-neutral-500">
          {label.toUpperCase()}
        </div>
        {valueContent}
        {disclaimer && (
          <div className="text-[11px] leading-tight text-neutral-400">{disclaimer}</div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="text-xs font-medium uppercase tracking-wider text-neutral-500 shrink-0">
          {label.toUpperCase()}
        </div>
        <div className="text-sm font-semibold text-neutral-900 min-w-0 text-right">
          {valueContent}
        </div>
      </div>
      {disclaimer && (
        <div className="mt-1.5 text-[11px] leading-tight text-neutral-400">{disclaimer}</div>
      )}
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
  stackedRows = false,
  priority = false,
  unoptimized = false,
  badge,
  onReportIssue,
}: ListingCardProps) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
      {badge && (
        <div className="absolute left-3 top-3 z-10 rounded-full bg-amber-500 px-3 py-1 text-xs font-semibold text-white shadow-sm">
          {badge}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,42%)_1fr]">
        {/* Left: Image — sizes="600px" so Vercel serves one size per image (fewer transformations) */}
        <div className="relative aspect-[4/3] w-full overflow-hidden bg-neutral-100 md:aspect-auto md:h-full md:min-h-0 md:rounded-l-2xl">
          <Image
            src={imageUrl}
            alt={imageAlt}
            fill
            sizes="600px"
            className="object-contain"
            priority={priority}
            unoptimized={unoptimized}
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
              <PillRow
                key={`${r.label}-${idx}`}
                label={r.label}
                value={r.value}
                selectable={r.selectable}
                listStyle={r.listStyle}
                disclaimer={r.disclaimer}
                stacked={stackedRows}
              />
            ))}
          </div>

          {onReportIssue && (
            <button
              type="button"
              onClick={onReportIssue}
              className="mt-3 self-start text-xs text-slate-400 underline hover:text-slate-600"
            >
              Report an issue
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
