import Link from "next/link";

const FEATURES = [
  {
    title: "Ranked Lead Lists",
    description:
      "Every home in your territory scored and ranked by likelihood of solar adoption. Our models are trained on 13 years of permit data using walk-forward validation — no look-ahead bias, no overfitting.",
  },
  {
    title: "Roof-Level Solar Potential",
    description:
      "Google Solar API data for every property — usable roof area, orientation, shade analysis, and an independent roof score so you know which homes have the best physical fit.",
  },
  {
    title: "Permit Monitoring",
    description:
      "Real-time alerts when new solar, roof, battery, or EV charger permits are filed. A new roof means a solar-ready lead. A neighbor's solar install means social proof is working for you.",
  },
  {
    title: "Built-In Workflow Tools",
    description:
      "Notes, tags, follow lists, action items, and contact management — all attached to each property. No exporting CSVs into a separate CRM. Your team works directly on the data.",
  },
  {
    title: "Email Enrichment",
    description:
      "Look up homeowner contact information on demand. Pay per lookup, no bulk commitments. 20 free credits included with every territory.",
  },
  {
    title: "Interactive Map Explorer",
    description:
      "Browse your entire territory visually. Filter by score, roof quality, tags, subdivision, and more. Color-coded dots show you where the highest-value leads cluster.",
  },
];

const DIFFERENTIATORS = [
  {
    heading: "Data science, not just data",
    body: "Most lead providers hand you a list filtered by home value and roof age. We build predictive models that learn which combinations of property attributes, neighborhood dynamics, permit history, and economic factors actually predict solar adoption. Our top-scored decile captures 37% of all future installs.",
  },
  {
    heading: "Validated on real outcomes",
    body: "We test our models the hard way: train on past years, predict the next year, check against actual permit filings. Every metric we share comes from out-of-sample validation across 13 years of data. We show you the range of performance, not a cherry-picked number.",
  },
  {
    heading: "One platform, not five tools",
    body: "Scored leads, roof analysis, permit alerts, workflow tools, and contact enrichment in one place. No stitching together a lead vendor, a CRM, a permit tracker, and an enrichment API. Less friction means your team actually uses the data.",
  },
  {
    heading: "Transparent methodology",
    body: "We publish how our models work, what features drive predictions, and where the data comes from. If a score looks wrong, you can understand why. No black boxes, no \"proprietary algorithm\" hand-waving.",
  },
];

export default function AboutPage() {
  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
              Solar Intelligence
            </h1>
            <p className="mt-2 text-lg text-slate-600">
              Smarter solar leads. Fewer wasted doors.
            </p>
          </div>
          <Link
            href="/homes"
            className="shrink-0 inline-flex items-center justify-center rounded-xl bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Explore Homes
          </Link>
        </div>

        <section className="mt-12">
          <p className="text-slate-700 leading-relaxed">
            Solar companies waste time and money knocking on doors that will never convert.
            We fix that. Solar Intelligence combines property records, satellite roof analysis,
            permit history, Census demographics, and machine learning to rank every home in
            your territory by how likely it is to go solar — before you make a single call.
          </p>
        </section>

        <section className="mt-14">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            What you get
          </h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-xl border border-neutral-200 bg-white p-5"
              >
                <h3 className="text-sm font-bold uppercase tracking-wider text-amber-600">
                  {f.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  {f.description}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            How we're different
          </h2>
          <div className="mt-6 flex flex-col gap-8">
            {DIFFERENTIATORS.map((d) => (
              <div key={d.heading}>
                <h3 className="text-base font-semibold text-slate-900">
                  {d.heading}
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">
                  {d.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14 rounded-xl border border-amber-200 bg-amber-50/60 p-6 text-center">
          <h2 className="text-lg font-bold text-slate-900">
            Ready to stop guessing?
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            See our territory pricing or jump straight into the data.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-3">
            <Link
              href="/pricing"
              className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              View Pricing
            </Link>
            <Link
              href="/homes"
              className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Explore Homes
            </Link>
          </div>
        </section>

        <p className="mt-10 text-xs text-slate-400">
          Data sourced from public records, Google Solar API, and Census Bureau.
          Inclusion does not indicate homeowner interest or contact consent.
          Actual conditions may vary.
        </p>
      </div>
    </main>
  );
}
