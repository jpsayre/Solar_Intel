import Link from "next/link";

export default function FAQPage() {
  const faqs = [
    {
      q: "What data sources do you use?",
      a: "We combine public property records (county assessor data, ownership, permits) with satellite imagery analysis. This allows us to verify roof orientation, detect existing solar panels, and assess shade conditions.",
    },
    {
      q: "What does 'qualified roof' mean?",
      a: "A qualified roof meets our criteria: single-family, owner-occupied home with no existing solar, minimal shade, and at least 30 m² of roof area in an East, South, or West facing orientation.",
    },
    {
      q: "Which areas do you cover?",
      a: "Coverage varies by region. We are actively expanding. Contact us to check availability for your target markets.",
    },
    {
      q: "How often is the data updated?",
      a: "We refresh our data periodically as new imagery and public records become available. Update frequency depends on the data source and region.",
    },
    {
      q: "Can I use this for door-to-door or cold outreach?",
      a: "Our data identifies properties that meet technical criteria. Inclusion does not imply homeowner interest or consent to contact. Always comply with local regulations, do-not-call lists, and homeowner preferences.",
    },
    {
      q: "How do I get access to the data?",
      a: "Reach out through our contact page. We can discuss your use case and provide information on data access options.",
    },
  ];

  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Frequently Asked Questions
        </h1>

        <div className="mt-12 space-y-8">
          {faqs.map((faq, i) => (
            <div
              key={i}
              className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm"
            >
              <h2 className="text-lg font-semibold text-slate-900">
                {faq.q}
              </h2>
              <p className="mt-3 text-slate-600">
                {faq.a}
              </p>
            </div>
          ))}
        </div>

        <p className="mt-12 text-center text-slate-600">
          Have more questions?{" "}
          <Link href="/contact" className="font-medium text-amber-600 underline hover:text-amber-700">
            Contact us
          </Link>
        </p>
      </div>
    </main>
  );
}
