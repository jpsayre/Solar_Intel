"use client";

import { useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";

const SOLAR_OPTIONS = [
  { value: "has_solar", label: "Property has solar panels" },
  { value: "no_solar", label: "Property does not have solar panels" },
] as const;

type Props = {
  homeIndex: string;
  onClose: () => void;
};

export default function ReportIssueModal({ homeIndex, onClose }: Props) {
  const [category] = useState("solar_status");
  const [solarChoice, setSolarChoice] = useState<string>(SOLAR_OPTIONS[0].value);

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    const { data: userData } = await supabaseBrowser.auth.getUser();
    const userId = userData?.user?.id ?? null;

    const { error: insertErr } = await supabaseBrowser.from("home_issues").insert({
      home_index: homeIndex,
      category,
      description: solarChoice === "has_solar"
        ? "Property has solar panels"
        : "Property does not have solar panels",
      user_id: userId,
    });

    setSubmitting(false);
    if (insertErr) {
      setError(insertErr.message);
    } else {
      setSubmitted(true);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-md rounded-2xl border border-neutral-200 bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {submitted ? (
          <div className="text-center">
            <p className="text-lg font-semibold text-slate-900">Issue reported</p>
            <p className="mt-1 text-sm text-slate-500">Thanks for helping improve our data.</p>
            <button
              onClick={onClose}
              className="mt-4 rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <h3 className="text-lg font-semibold text-slate-900">Report an issue</h3>
            <p className="mt-0.5 text-xs text-slate-400">{homeIndex}</p>

            <div className="mt-4 space-y-2">
              {SOLAR_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors ${
                    solarChoice === opt.value
                      ? "border-amber-400 bg-amber-50 text-slate-900"
                      : "border-neutral-200 text-slate-600 hover:border-neutral-300"
                  }`}
                >
                  <input
                    type="radio"
                    name="solar_status"
                    value={opt.value}
                    checked={solarChoice === opt.value}
                    onChange={(e) => setSolarChoice(e.target.value)}
                    className="accent-amber-500"
                  />
                  {opt.label}
                </label>
              ))}
            </div>

            {error && (
              <p className="mt-2 text-sm text-red-600">{error}</p>
            )}

            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50"
              >
                {submitting ? "Submitting..." : "Submit"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
