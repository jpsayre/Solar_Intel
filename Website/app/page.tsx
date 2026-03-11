import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col">
      {/* Hero */}
      <section className="px-4 py-20 sm:px-6 sm:py-28">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Data-Driven Solar Property Intelligence
          </h1>
          <p className="mt-6 text-lg text-slate-600 sm:text-xl">
            We use public records and satellite imagery to identify qualified residential roofs for solar installation—single family, owner-occupied, with optimal orientation and no existing panels.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              href="/purchase"
              className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              View pricing
            </Link>
            <Link
              href="/about"
              className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3 text-base font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Learn more
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3 text-base font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Get in touch
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-slate-200/80 bg-white/50 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            How we identify qualified roofs
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">Public records</h3>
              <p className="mt-2 text-sm text-slate-600">
                Property data, ownership, and permit history to ensure single-family, owner-occupied homes.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0h.5a2.5 2.5 0 002.5-2.5V3.935M12 12a2 2 0 104 0 2 2 0 00-4 0z" />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">Satellite imagery</h3>
              <p className="mt-2 text-sm text-slate-600">
                Roof orientation, shade analysis, and solar panel detection from high-resolution imagery.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm sm:col-span-2 lg:col-span-1">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">Qualified criteria</h3>
              <p className="mt-2 text-sm text-slate-600">
                East, south, or west facing roof segments ≥30 m², minimal shade, no existing solar.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm sm:p-12">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            Ready to explore qualified roofs?
          </h2>
          <p className="mt-4 text-slate-600">
            Contact us to learn about our data and how it can support your solar sales or installation workflow.
          </p>
          <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/purchase"
              className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              View pricing
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3 text-base font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Contact us
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
