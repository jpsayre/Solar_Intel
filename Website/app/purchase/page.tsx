import Link from "next/link";

export default function PurchasePage() {
  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Purchase
        </h1>

        <p className="mt-8 text-slate-700">
          Our pricing is $800 per expected sale. Each package of homes is sized to return at least one expected sale in the current year. Higher tiers are expected to do so with less outreach required. We include a small buffer of homes to account for randomness.
        </p>

        <p className="mt-4 text-slate-700">
          Packages are for exclusive use of the buyer for 90 days from date of sale.
        </p>

        <p className="mt-4 text-slate-700">
          If after the exclusive period is over and after contacting all leads (with documented outreach), you close zero installs, we’ll provide 10 additional leads free.
        </p>

        <div className="mt-12 space-y-8">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-900">Tier 1</h2>
            <p className="mt-2 text-slate-600">
              These homes are in the top 5%. They&apos;re expected to generate at least 1 sale per 19 outreaches.
            </p>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">25 Tier 1 Homes</span>
              <span className="text-xl font-semibold text-amber-600">$800</span>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-900">Tier 2</h2>
            <p className="mt-2 text-slate-600">
              These homes are in the top 5–10% range. They&apos;re expected to generate at least 1 sale per 24 outreaches.
            </p>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">30 Tier 2 Homes</span>
              <span className="text-xl font-semibold text-amber-600">$800</span>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-900">Tier 3</h2>
            <p className="mt-2 text-slate-600">
              These homes are in the top 10–20% range. They&apos;re expected to generate at least 1 sale per 33 outreaches.
            </p>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">40 Tier 3 Homes</span>
              <span className="text-xl font-semibold text-amber-600">$800</span>
            </div>
          </div>
        </div>

        <div className="mt-12 rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-4">
          <p className="text-sm text-slate-600">
            Want to learn more about how we rank homes and what lift and capture rates mean? See our{" "}
            <Link href="/about#lifts-and-capture" className="font-medium text-amber-600 underline hover:text-amber-700">
              About page
            </Link>
            .
          </p>
        </div>

        <div className="mt-12">
          <Link
            href="/contact"
            className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Contact us to purchase
          </Link>
        </div>
      </div>
    </main>
  );
}
