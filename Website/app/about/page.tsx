export default function AboutPage() {
  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          About Solar Intelligence
        </h1>

        <p className="mt-8 text-slate-700">
          Solar Intelligence uses public records and satellite imagery to identify residential properties that meet our qualified roof criteria. Our goal is to help solar installers, sales teams, and developers focus their outreach on homes that are most likely to be viable candidates for solar installation.
        </p>

        <h2 className="mt-12 text-xl font-semibold text-slate-900">Our criteria</h2>
        <p className="mt-4 text-slate-700">
          We filter for homes that meet the following conditions:
        </p>
        <ul className="mt-4 list-disc space-y-2 pl-6 text-slate-700">
          <li>Single family home</li>
          <li>Owner occupied</li>
          <li>No or minimal shade concerns</li>
          <li>No existing solar panel installation</li>
          <li>Roof segment a minimum of 30 m² (323 ft²) in the orientation(s) specified</li>
        </ul>

        <h2 className="mt-12 text-xl font-semibold text-slate-900">Roof orientations</h2>
        <p className="mt-4 text-slate-700">
          We support East, South, and West facing roof segments:
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-slate-700">
          <li>East Facing: 80–140°</li>
          <li>South Facing: 140–220°</li>
          <li>West Facing: 220–280°</li>
        </ul>

        <div className="mt-10 rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-4">
          <p className="text-sm text-slate-600">
            <strong>Note:</strong> Data changes over time, and imagery analysis is impacted by image quality. Actual conditions may vary. Inclusion on our reports does not indicate homeowner interest in a solar system or contact consent.
          </p>
        </div>

        <h2 id="lifts-and-capture" className="mt-12 text-xl font-semibold text-slate-900">
          Lifts and capture rates
        </h2>
        <p className="mt-4 text-slate-700">
          We use machine learning models trained on historical solar adoption data to score each home. Two key metrics describe how well our rankings perform:
        </p>
        <ul className="mt-4 list-disc space-y-2 pl-6 text-slate-700">
          <li>
            <strong>Lift</strong> — How much higher the adoption rate is in a given segment compared to the baseline (random selection). A 3x lift at the top 10% means homes in that segment adopt solar at 3× the overall rate.
          </li>
          <li>
            <strong>Capture rate</strong> — What share of all adopters fall within that segment. If the top 10% captures 35% of adopters, you find more than a third of future solar customers by targeting just 10% of homes.
          </li>
        </ul>
        <p className="mt-6 text-slate-700">
          Our walk-forward validation across multiple years shows consistent performance. Representative values from our model (averaged across years):
        </p>
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[320px] border-collapse rounded-xl border border-slate-200">
            <thead>
              <tr className="bg-slate-50">
                <th className="border-b border-slate-200 px-4 py-3 text-left text-sm font-semibold text-slate-900">
                  Segment
                </th>
                <th className="border-b border-slate-200 px-4 py-3 text-right text-sm font-semibold text-slate-900">
                  Lift
                </th>
                <th className="border-b border-slate-200 px-4 py-3 text-right text-sm font-semibold text-slate-900">
                  Capture rate
                </th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-slate-100">
                <td className="px-4 py-3 text-sm text-slate-700">Top 5%</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~4–6×</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~25–35%</td>
              </tr>
              <tr className="border-b border-slate-100">
                <td className="px-4 py-3 text-sm text-slate-700">Top 10%</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~3–4×</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~30–45%</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-sm text-slate-700">Top 20%</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~2.5–3×</td>
                <td className="px-4 py-3 text-right text-sm font-medium text-slate-900">~45–60%</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-slate-500">
          Results vary by year and region. Higher tiers (top 5%) concentrate more adopters per outreach; lower tiers (top 20%) capture more total adopters with more outreach required.
        </p>

        <h2 className="mt-12 text-xl font-semibold text-slate-900">Coverage</h2>
        <p className="mt-4 text-slate-700">
          We are continuously expanding our coverage. Contact us to learn which counties and regions are currently supported.
        </p>
      </div>
    </main>
  );
}
