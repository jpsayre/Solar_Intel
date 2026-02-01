"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

type HomeNote = {
  id: number;
  home_index: string;
  author_id: string;
  body: string;
  created_at: string;
  updated_at: string;
};

function formatNoteTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function HomeDetailPage() {
  const router = useRouter();
  const params = useParams<{ index: string }>();

  const [row, setRow] = useState<HomeRow | null>(null);
  const [imgUrl, setImgUrl] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [imgErr, setImgErr] = useState<string | null>(null);

  const [notes, setNotes] = useState<HomeNote[] | null>(null);
  const [notesErr, setNotesErr] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let alive = true;

    async function load() {
      setErr(null);
      setImgErr(null);
      setImgUrl("");
      setRow(null);

      // 1) Ensure logged in
      const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
      if (userErr) {
        if (alive) setErr(userErr.message);
        return;
      }
      if (!userData.user) {
        router.push("/login");
        return;
      }

      // 2) Fetch the row by string index (DO NOT Number(...) this)
      const idx = params.index;

      const { data, error } = await supabaseBrowser
        .from("homes")
        .select("*")
        .eq("index", idx)
        .single();

      if (!alive) return;
      if (error) {
        setErr(error.message);
        return;
      }

      setRow(data as HomeRow);

      // 3) Create a signed URL for the image
      const path = `${(data as HomeRow).original_index}.png`;

      const signed = await supabaseBrowser.storage
        .from(BUCKET)
        .createSignedUrl(path, 60 * 30); // 30 minutes

      if (!alive) return;

      if (signed.error) {
        console.error("SIGNED URL ERROR (detail)", { bucket: BUCKET, path, error: signed.error });
        setImgErr(signed.error.message ?? "Image error");
        setImgUrl("");
      } else {
        setImgUrl(signed.data?.signedUrl ?? "");
      }
    }

    load();

    return () => {
      alive = false;
    };
  }, [params.index, router]);

  const loadNotes = useCallback(async () => {
    const idx = params.index;
    if (!idx) return;
    setNotesErr(null);
    setNotes(null);
    const { data, error } = await supabaseBrowser
      .from("home_notes")
      .select("id, home_index, author_id, body, created_at, updated_at")
      .eq("home_index", idx)
      .order("created_at", { ascending: false });
    if (error) {
      setNotesErr(error.message);
      setNotes([]);
      return;
    }
    setNotes((data ?? []) as HomeNote[]);
  }, [params.index]);

  useEffect(() => {
    let alive = true;
    if (!row || !params.index) return;
    loadNotes().then(() => {
      if (!alive) return;
    });
    return () => {
      alive = false;
    };
  }, [row, params.index, loadNotes]);

  async function handleAddNote(e: React.FormEvent) {
    e.preventDefault();
    const body = noteBody.trim();
    if (!body || !params.index) return;
    const { data: userData } = await supabaseBrowser.auth.getUser();
    if (!userData.user) return;
    setSubmitting(true);
    setNotesErr(null);
    const { error } = await supabaseBrowser.from("home_notes").insert({
      home_index: params.index,
      author_id: userData.user.id,
      body,
    });
    setSubmitting(false);
    if (error) {
      setNotesErr(error.message);
      return;
    }
    setNoteBody("");
    await loadNotes();
  }

  if (err) {
    return (
      <main className="min-h-screen px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-red-200 bg-red-50 px-6 py-4 text-red-800">
          <p className="font-medium">Something went wrong</p>
          <p className="mt-1 text-sm opacity-90">{err}</p>
        </div>
      </main>
    );
  }
  if (!row) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
          <p className="text-slate-600">Loading…</p>
        </div>
      </main>
    );
  }

  const { addressLine1, addressLine2, detailRows } = buildListingCardData(row);

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <Link
          href="/homes"
          className="mb-6 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
        >
          ← Back to listings
        </Link>

        <ListingCard
          addressLine1={addressLine1}
          addressLine2={addressLine2}
          imageUrl={imgUrl || "/window.svg"}
          imageAlt={imgUrl ? `Home ${row.original_index}` : imgErr ? "No image" : "Loading…"}
          rows={detailRows}
        />

        <section className="mt-10">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">Comments</h2>
          <p className="mb-4 text-sm text-slate-500">
            Notes are visible only to users in your organization.
          </p>

          <form onSubmit={handleAddNote} className="mb-6">
            <label htmlFor="note-body" className="sr-only">
              Add a comment
            </label>
            <textarea
              id="note-body"
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Add a comment…"
              rows={3}
              disabled={submitting}
              className="mb-3 w-full rounded-xl border border-neutral-200 bg-white px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={submitting || !noteBody.trim()}
              className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 disabled:opacity-60 disabled:hover:bg-amber-500"
            >
              {submitting ? "Adding…" : "Add comment"}
            </button>
          </form>

          {notesErr && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {notesErr}
            </div>
          )}

          {notes === null ? (
            <p className="text-sm text-slate-500">Loading comments…</p>
          ) : notes.length === 0 ? (
            <p className="text-sm text-slate-500">No comments yet. Add one above.</p>
          ) : (
            <ul className="flex flex-col gap-4">
              {notes.map((note) => (
                <li
                  key={note.id}
                  className="rounded-xl border border-neutral-200 bg-neutral-50/80 px-4 py-3"
                >
                  <p className="whitespace-pre-wrap text-sm text-slate-900">{note.body}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    {formatNoteTimestamp(note.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
