"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

export default function FollowsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});
  const [followedSet, setFollowedSet] = useState<Set<string>>(new Set());
  const [userId, setUserId] = useState<string | null>(null);

  const loadFollows = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
    if (userErr || !userData.user) {
      router.push("/login");
      return;
    }
    setUserId(userData.user.id);

    const { data: followData, error: followErr } = await supabaseBrowser
      .from("user_follows")
      .select("home_index")
      .eq("user_id", userData.user.id);

    if (followErr) {
      setErr(followErr.message);
      setRows([]);
      setLoading(false);
      return;
    }

    const indices = (followData ?? []).map((r: { home_index: string }) => r.home_index);
    setFollowedSet(new Set(indices));

    if (indices.length === 0) {
      setRows([]);
      setLoading(false);
      return;
    }

    const { data: homesData, error: homesErr } = await supabaseBrowser
      .from("homes")
      .select("*")
      .in("index", indices);

    if (homesErr) {
      setErr(homesErr.message);
      setRows([]);
      setLoading(false);
      return;
    }

    setRows((homesData ?? []) as HomeRow[]);
    setLoading(false);
  }, [router]);

  useEffect(() => {
    loadFollows();
  }, [loadFollows]);

  useEffect(() => {
    let alive = true;
    if (!rows?.length) return;

    const missing = rows
      .map((r) => r.original_index)
      .filter((oi) => imgUrls[oi] === undefined && imgErrors[oi] === undefined);
    if (missing.length === 0) return;

    Promise.all(
      missing.map(async (oi) => {
        const { data, error } = await supabaseBrowser.storage
          .from(BUCKET)
          .createSignedUrl(`${oi}.png`, 60 * 30);
        if (error) return { oi, url: "", err: error.message };
        return { oi, url: data?.signedUrl ?? "", err: "" };
      })
    ).then((results) => {
      if (!alive) return;
      const nextUrls = { ...imgUrls };
      const nextErrs = { ...imgErrors };
      for (const r of results) {
        if (r.url) nextUrls[r.oi] = r.url;
        else nextErrs[r.oi] = r.err || "error";
      }
      setImgUrls(nextUrls);
      setImgErrors(nextErrs);
    });
    return () => { alive = false; };
  }, [rows, imgUrls, imgErrors]);

  const toggleFollow = useCallback(
    async (homeIndex: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!userId) return;
      await supabaseBrowser.from("user_follows").delete().eq("user_id", userId).eq("home_index", homeIndex);
      setFollowedSet((prev) => new Set([...prev].filter((x) => x !== homeIndex)));
      setRows((prev) => (prev ?? []).filter((r) => r.index !== homeIndex));
    },
    [userId]
  );

  if (loading) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
        <p className="mt-3 text-slate-600">Loading…</p>
      </main>
    );
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

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Following</h1>
          <p className="mt-1 text-sm text-slate-600">Homes you follow. Click a card to open the home.</p>
        </header>

        {!rows?.length ? (
          <div className="rounded-2xl border border-neutral-200 bg-neutral-50/80 px-6 py-12 text-center text-slate-600">
            <p className="font-medium">No followed homes</p>
            <p className="mt-1 text-sm">Follow homes from the Homes page to see them here.</p>
            <Link
              href="/homes"
              className="mt-4 inline-flex rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-600"
            >
              Browse Homes
            </Link>
          </div>
        ) : (
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
                    followState={{
                      isFollowed: true,
                      onToggle: (ev) => toggleFollow(r.index, ev),
                    }}
                    unoptimized
                  />
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
