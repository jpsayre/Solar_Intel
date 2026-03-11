"use client";

import { useState } from "react";

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    company: "",
    message: "",
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // For now, just show success. In production you'd POST to an API or form service.
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-4 py-16 sm:px-6">
        <div className="mx-auto w-full max-w-md rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="mt-4 text-xl font-bold text-slate-900">Thank you</h2>
          <p className="mt-2 text-slate-600">
            We&apos;ve received your message and will get back to you soon.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col px-4 py-16 sm:px-6">
      <div className="mx-auto w-full max-w-md">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Contact us
        </h1>
        <p className="mt-4 text-slate-600">
          Interested in our data or have questions? Send us a message.
        </p>

        <form
          onSubmit={handleSubmit}
          className="mt-10 rounded-3xl border border-slate-200/80 bg-white p-8 shadow-sm"
        >
          <div className="flex flex-col gap-6">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Name
              </span>
              <input
                type="text"
                placeholder="Your name"
                value={formData.name}
                onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))}
                className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Email
              </span>
              <input
                type="email"
                placeholder="you@example.com"
                value={formData.email}
                onChange={(e) => setFormData((d) => ({ ...d, email: e.target.value }))}
                className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Company (optional)
              </span>
              <input
                type="text"
                placeholder="Your company"
                value={formData.company}
                onChange={(e) => setFormData((d) => ({ ...d, company: e.target.value }))}
                className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                Message
              </span>
              <textarea
                placeholder="Tell us about your needs..."
                value={formData.message}
                onChange={(e) => setFormData((d) => ({ ...d, message: e.target.value }))}
                rows={5}
                className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20 resize-none"
              />
            </label>
          </div>
          <button
            type="submit"
            className="mt-6 w-full rounded-xl bg-amber-500 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          >
            Send message
          </button>
        </form>
      </div>
    </main>
  );
}
