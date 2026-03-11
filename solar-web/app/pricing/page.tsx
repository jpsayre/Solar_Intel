export default function PricingPage() {
  return (
    <main className="min-h-screen px-4 py-12 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-10 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Pricing
          </h1>
          <p className="mt-3 text-lg text-slate-600">
            ML-ranked solar leads with roof scoring, interactive maps, and team tools.
          </p>
        </header>

        {/* Platform tiers */}
        <section className="mb-16">
          <h2 className="mb-6 text-xl font-semibold text-slate-900">
            Platform Access
          </h2>
          <p className="mb-6 text-sm text-slate-500">
            Graduated pricing &mdash; like tax brackets, each tier only applies to homes in that range.
            Year 1 includes full dataset build, scoring, and platform access.
            Renewals cover quarterly score updates and continued platform access at a reduced rate.
          </p>
          <div className="overflow-hidden rounded-xl border border-neutral-200">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-neutral-200 bg-slate-50">
                  <th className="px-5 py-3 font-semibold text-slate-700">Homes</th>
                  <th className="px-5 py-3 font-semibold text-slate-700">1st Year</th>
                  <th className="px-5 py-3 font-semibold text-slate-700">1st Year Range</th>
                  <th className="px-5 py-3 font-semibold text-slate-700">Yearly Renewal</th>
                  <th className="px-5 py-3 font-semibold text-slate-700">Renewal Range</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                <tr>
                  <td className="px-5 py-4 text-slate-700">First 5,000</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$1.00 / home</td>
                  <td className="px-5 py-4 text-slate-500">$0 &ndash; $5,000</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$1.00 / home</td>
                  <td className="px-5 py-4 text-slate-500">$0 &ndash; $5,000</td>
                </tr>
                <tr>
                  <td className="px-5 py-4 text-slate-700">5,001 &ndash; 20,000</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.25 / home</td>
                  <td className="px-5 py-4 text-slate-500">$5,000 &ndash; $8,750</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.18 / home</td>
                  <td className="px-5 py-4 text-slate-500">$5,000 &ndash; $7,700</td>
                </tr>
                <tr>
                  <td className="px-5 py-4 text-slate-700">20,001 &ndash; 50,000</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.15 / home</td>
                  <td className="px-5 py-4 text-slate-500">$8,750 &ndash; $13,250</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.10 / home</td>
                  <td className="px-5 py-4 text-slate-500">$7,700 &ndash; $10,700</td>
                </tr>
                <tr>
                  <td className="px-5 py-4 text-slate-700">50,001 &ndash; 150,000</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.10 / home</td>
                  <td className="px-5 py-4 text-slate-500">$13,250 &ndash; $23,250</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.07 / home</td>
                  <td className="px-5 py-4 text-slate-500">$10,700 &ndash; $17,700</td>
                </tr>
                <tr>
                  <td className="px-5 py-4 text-slate-700">150,001+</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.06 / home</td>
                  <td className="px-5 py-4 text-slate-500">$23,250+</td>
                  <td className="px-5 py-4 text-slate-900 font-semibold">$0.04 / home</td>
                  <td className="px-5 py-4 text-slate-500">$17,700+</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="mt-4 rounded-lg bg-slate-50 px-5 py-4 text-sm text-slate-600">
            <div className="font-semibold text-slate-700 mb-2">Example territories (1st year)</div>
            <ul className="space-y-1">
              <li>Boulder County (~16k homes): <span className="font-semibold text-slate-900">$7,750</span> &mdash; 5,000 &times; $1.00 + 11,000 &times; $0.25</li>
              <li>San Diego (~100k homes): <span className="font-semibold text-slate-900">$18,250</span> &mdash; 5k &times; $1.00 + 15k &times; $0.25 + 30k &times; $0.15 + 50k &times; $0.10</li>
            </ul>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Pricing based on number of qualified residential properties in your territory. Minimum territory size is one city or municipality.
          </p>
        </section>

        {/* Enrichment credits */}
        <section className="mb-16">
          <h2 className="mb-6 text-xl font-semibold text-slate-900">
            Email Enrichment
          </h2>
          <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 px-5 py-5">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">$2.00</span>
              <span className="text-sm text-slate-500">/ home</span>
            </div>
            <p className="mt-2 text-sm text-slate-600">
              Look up email addresses for homeowners directly from the platform. Each credit covers both owners on record. Only charged on successful matches.
            </p>
            <p className="mt-3 text-sm text-slate-600">
              <span className="font-semibold text-slate-900">20 free credits</span> included with every platform subscription.
            </p>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Credits never expire. No charge for lookups that don&apos;t return a match.
          </p>
        </section>

        {/* What's included */}
        <section className="mb-16">
          <h2 className="mb-6 text-xl font-semibold text-slate-900">
            What&apos;s Included
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { title: "ML Ranking Scores", desc: "Every home scored 1\u2013100 based on solar adoption likelihood using permit history, neighbor patterns, and property data." },
              { title: "Roof Quality Scores", desc: "Roof orientation, area, and sun exposure analyzed via Google Solar API. Scored 1\u2013100." },
              { title: "Interactive Map", desc: "Color-coded map with filtering by score, roof orientation, subdivision, and team-assigned interest levels." },
              { title: "Team Collaboration", desc: "Follow homes, add tags, track action items, log notes, and rate solar/battery interest across your sales team." },
              { title: "Quarterly Updates", desc: "Scores refreshed quarterly as new permits are filed and neighbor adoption patterns shift." },
              { title: "Email Enrichment", desc: "Look up homeowner emails on demand. Pay per successful match, no wasted credits." },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-xl border border-neutral-200 bg-neutral-50/80 px-5 py-4"
              >
                <div className="font-semibold text-slate-900">{item.title}</div>
                <div className="mt-1 text-sm text-slate-600">{item.desc}</div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="rounded-2xl border border-amber-200 bg-amber-50/60 px-6 py-8 text-center">
          <h2 className="text-xl font-bold text-slate-900">
            Ready to target your best solar prospects?
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Contact us to set up your territory and get started.
          </p>
          <a
            href="mailto:jeff@solarintel.com"
            className="mt-5 inline-block rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Get in touch
          </a>
        </section>
      </div>
    </main>
  );
}
