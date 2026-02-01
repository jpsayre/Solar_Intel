import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-16">
      <div className="mx-auto max-w-lg text-center">
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
          Solar
        </h1>
        <p className="mt-4 text-lg text-slate-600">
          Browse solar property listings and insights.
        </p>
        <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-6 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Sign in
          </Link>
          <Link
            href="/homes"
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300 focus:ring-offset-2"
          >
            View listings
          </Link>
        </div>
      </div>
    </main>
  );
}
