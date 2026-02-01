"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";
const PAGE_SIZE = 25;

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

export default function HomesPage() {
  const router = useRouter();

  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // signed urls keyed by original_index
  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    let alive = true;

    async function loadRows() {
      setErr(null);
      setRows(null);

      // 1) Require login
      const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
      if (userErr) {
        if (alive) setErr(userErr.message);
        return;
      }
      if (!userData.user) {
        router.push("/login");
        return;
      }

      // 2) Fetch full rows for card data (address, owner, etc.)
      const { data, error } = await supabaseBrowser
        .from("homes")
        .select("*")
        .order("index", { ascending: true })
        .limit(PAGE_SIZE);

      if (!alive) return;

      if (error) {
        setErr(error.message);
        setRows([]);
        return;
      }

      setRows((data ?? []) as HomeRow[]);
    }

    loadRows();

    return () => {
      alive = false;
    };
  }, [router]);

  useEffect(() => {
    let alive = true;

    async function signImages() {
      if (!rows || rows.length === 0) return;

      const missing = rows
        .map((r) => r.original_index)
        .filter((oi) => imgUrls[oi] === undefined && imgErrors[oi] === undefined);

      if (missing.length === 0) return;

      const results = await Promise.all(
        missing.map(async (oi) => {
          const path = `${oi}.png`; // mapping you confirmed

          const { data, error } = await supabaseBrowser.storage
            .from(BUCKET)
            .createSignedUrl(path, 60 * 30); // 30 minutes

          if (error) {
            console.error("SIGNED URL ERROR (list)", { bucket: BUCKET, path, error });
            return { oi, url: "", errorMsg: error.message ?? "storage error" };
          }

          return { oi, url: data?.signedUrl ?? "", errorMsg: "" };
        })
      );

      if (!alive) return;

      const nextUrls = { ...imgUrls };
      const nextErrs = { ...imgErrors };

      for (const r of results) {
        if (r.url) nextUrls[r.oi] = r.url;
        else nextErrs[r.oi] = r.errorMsg || "missing image";
      }

      setImgUrls(nextUrls);
      setImgErrors(nextErrs);
    }

    signImages();

    return () => {
      alive = false;
    };
  }, [rows, imgUrls, imgErrors]);

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
  if (rows === null) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
          <p className="text-slate-600">Loading listings…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Homes</h1>
          <button
            onClick={async () => {
              await supabaseBrowser.auth.signOut();
              router.push("/login");
            }}
            className="w-fit rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-800"
          >
            Log out
          </button>
        </header>

        <div className="flex flex-col gap-8">
          {rows.map((r) => {
            const url = imgUrls[r.original_index];
            const e = imgErrors[r.original_index];
            const imageUrl = url || "/window.svg";
            const imageAlt = url ? `Home ${r.original_index}` : e ? "No access / not found" : "Loading…";
            const { addressLine1, addressLine2, detailRows } = buildListingCardData(r);

            return (
              <Link
                key={r.index}
                href={`/homes/${encodeURIComponent(r.index)}`}
                className="block rounded-3xl text-inherit no-underline transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/60"
              >
                <ListingCard
                  addressLine1={addressLine1}
                  addressLine2={addressLine2}
                  imageUrl={imageUrl}
                  imageAlt={imageAlt}
                  rows={detailRows}
                />
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}
