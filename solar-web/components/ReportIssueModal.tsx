"use client";

import { useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";

const CATEGORIES = [
  { value: "permit_issue", label: "Permit issue" },
  { value: "solar_status", label: "Solar status" },
  { value: "image_issue", label: "Image issue" },
  { value: "home_info", label: "Home info" },
  { value: "other", label: "Other" },
] as const;

type Props = {
  homeIndex: string;
  onClose: () => void;
};

export default function ReportIssueModal({ homeIndex, onClose }: Props) {
  const [category, setCategory] = useState<string>(CATEGORIES[0].value);
  const [description, setDescription] = useState("");
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
      description: description.trim() || null,
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

            <label className="mt-4 block">
              <span className="text-sm font-medium text-slate-700">Category</span>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="mt-3 block">
              <span className="text-sm font-medium text-slate-700">
                Description <span className="font-normal text-slate-400">(optional)</span>
              </span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="What looks wrong?"
                className="mt-1 block w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
            </label>

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
