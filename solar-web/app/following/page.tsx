"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData, buildFollowingCardRows } from "@/lib/cardData";
import { indexToImagePath } from "@/lib/imagePath";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

type OrgHomeRow = {
  home_index: string;
  tags: string[] | null;
  interest_in_solar: string | null;
  interest_in_battery: string | null;
  [key: string]: unknown;
};

type ContactRow = {
  home_index: string;
  preferred_name: string | null;
  phone_number: string | null;
  email: string | null;
};

type ActionItemRow = {
  home_index: string;
  body: string | null;
  completed: boolean;
};

type HomeNoteRow = {
  home_index: string;
  body: string;
  created_at: string;
  [key: string]: unknown;
};

export default function FollowingPage() {
  const router = useRouter();
  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [imgUrls, setImgUrls] = useState<Record<number, string>>({});
  const [imgErrors, setImgErrors] = useState<Record<number, string>>({});
  const [followedSet, setFollowedSet] = useState<Set<string>>(new Set());
  const [userId, setUserId] = useState<string | null>(null);
  const [orgDataByIndex, setOrgDataByIndex] = useState<Record<string, { tags: string[]; contacts: ContactRow[]; actionItems: ActionItemRow[] }>>({});
  const [latestNoteByIndex, setLatestNoteByIndex] = useState<Record<string, { body: string }>>({});
  const [searchText, setSearchText] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [excludeTagFilter, setExcludeTagFilter] = useState("");
  const [excludeDoNotContact, setExcludeDoNotContact] = useState(true);

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
      setOrgDataByIndex({});
      setLatestNoteByIndex({});
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

    const { data: profile } = await supabaseBrowser
      .from("profiles")
      .select("org_id")
      .eq("user_id", userData.user.id)
      .maybeSingle();

    const orgId = profile?.org_id as string | undefined;
    const orgByIndex: Record<string, { tags: string[]; contacts: ContactRow[]; actionItems: ActionItemRow[] }> = {};
    if (orgId && indices.length > 0) {
      const [orgHomeRes, contactsRes, actionItemsRes] = await Promise.all([
        supabaseBrowser
          .from("org_home")
          .select("home_index, tags")
          .eq("org_id", orgId)
          .in("home_index", indices),
        supabaseBrowser
          .from("org_home_contacts")
          .select("home_index, preferred_name, phone_number, email")
          .eq("org_id", orgId)
          .in("home_index", indices),
        supabaseBrowser
          .from("org_home_action_items")
          .select("home_index, body, completed")
          .eq("org_id", orgId)
          .in("home_index", indices),
      ]);

      // Initialize entries from org_home tags
      for (const row of (orgHomeRes.data ?? []) as OrgHomeRow[]) {
        orgByIndex[row.home_index] = { tags: row.tags ?? [], contacts: [], actionItems: [] };
      }
      // Attach contacts
      for (const c of (contactsRes.data ?? []) as ContactRow[]) {
        if (!orgByIndex[c.home_index]) orgByIndex[c.home_index] = { tags: [], contacts: [], actionItems: [] };
        orgByIndex[c.home_index].contacts.push(c);
      }
      // Attach action items
      for (const a of (actionItemsRes.data ?? []) as ActionItemRow[]) {
        if (!orgByIndex[a.home_index]) orgByIndex[a.home_index] = { tags: [], contacts: [], actionItems: [] };
        orgByIndex[a.home_index].actionItems.push(a);
      }
    }
    setOrgDataByIndex(orgByIndex);

    const latestByIndex: Record<string, { body: string }> = {};
    if (indices.length > 0) {
      const { data: notesData } = await supabaseBrowser
        .from("home_notes")
        .select("home_index, body, created_at")
        .in("home_index", indices)
        .order("created_at", { ascending: false });
      const notes = (notesData ?? []) as HomeNoteRow[];
      for (const n of notes) {
        if (latestByIndex[n.home_index] === undefined) {
          latestByIndex[n.home_index] = { body: n.body };
        }
      }
    }
    setLatestNoteByIndex(latestByIndex);

    setLoading(false);
  }, [router]);

  useEffect(() => {
    loadFollows();
  }, [loadFollows]);

  useEffect(() => {
    let alive = true;
    if (!rows?.length) return;

    const missingRows = rows.filter(
      (r) => imgUrls[r.original_index] === undefined && imgErrors[r.original_index] === undefined
    );
    if (missingRows.length === 0) return;

    Promise.all(
      missingRows.map(async (r) => {
        const path = indexToImagePath(r.index);
        const { data, error } = await supabaseBrowser.storage
          .from(BUCKET)
          .createSignedUrl(path, 60 * 30);
        if (error) return { oi: r.original_index, url: "", err: error.message };
        return { oi: r.original_index, url: data?.signedUrl ?? "", err: "" };
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
          <p className="mt-1 text-sm text-slate-600">Homes you follow. Click a card to edit.</p>
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
          <>
            <div className="mb-6 rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-700">Filter cards</h2>
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <label className="flex flex-col gap-1 sm:col-span-1">
                    <span className="text-xs font-medium text-slate-500">Search (address, owner, comment, tags)</span>
                    <input
                      type="text"
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      placeholder="Type to search…"
                      className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-slate-500">Filter by tag</span>
                    <input
                      type="text"
                      value={tagFilter}
                      onChange={(e) => setTagFilter(e.target.value)}
                      placeholder="e.g. hot-lead"
                      className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-slate-500">Exclude tags</span>
                    <input
                      type="text"
                      value={excludeTagFilter}
                      onChange={(e) => setExcludeTagFilter(e.target.value)}
                      placeholder="e.g. not interested"
                      className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </label>
                </div>
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={excludeDoNotContact}
                    onChange={(e) => setExcludeDoNotContact(e.target.checked)}
                    className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                  />
                  <span className="text-sm text-slate-600">Exclude do not contact homes</span>
                </label>
              </div>
            </div>

            <div className="flex flex-col gap-8">
            {(() => {
              const searchLower = searchText.trim().toLowerCase();
              const tagLower = tagFilter.trim().toLowerCase();
              const excludeLower = excludeTagFilter.trim().toLowerCase();
              const filtered = rows.filter((r) => {
                const orgData = orgDataByIndex[r.index];
                const tags: string[] = (orgData?.tags ?? []).map((t) => t.trim().toLowerCase());
                if (tagLower) {
                  if (!tags.some((tag) => tag.startsWith(tagLower))) return false;
                }
                if (excludeLower) {
                  if (tags.some((tag) => tag.startsWith(excludeLower))) return false;
                }
                if (excludeDoNotContact && tags.some((tag) => tag.startsWith("do not contact"))) return false;
                if (!searchLower) return true;
                const { addressLine1, addressLine2 } = buildListingCardData(r);
                const latestNote = latestNoteByIndex[r.index];
                const detailRows = buildFollowingCardRows(r, orgData ?? null, latestNote);
                const cardText = [
                  addressLine1,
                  addressLine2,
                  ...detailRows.map((row) => row.value),
                ].join(" ").toLowerCase();
                return cardText.includes(searchLower);
              });
              if (filtered.length === 0) {
                return (
                  <div className="rounded-2xl border border-neutral-200 bg-neutral-50/80 px-6 py-12 text-center text-slate-600">
                    <p className="font-medium">No cards match the filter</p>
                    <p className="mt-1 text-sm">Try different search text or tag.</p>
                  </div>
                );
              }
              return filtered.map((r) => {
              const url = imgUrls[r.original_index];
              const e = imgErrors[r.original_index];
              const imageUrl = url || "/window.svg";
              const imageAlt = url ? `Home ${r.original_index}` : e ? "No access / not found" : "Loading…";
              const { addressLine1, addressLine2 } = buildListingCardData(r);
              const orgData = orgDataByIndex[r.index];
              const latestNote = latestNoteByIndex[r.index];
              const detailRows = buildFollowingCardRows(r, orgData ?? null, latestNote);
              return (
                <Link
                  key={r.index}
                  href={`/homes/${encodeURIComponent(r.index)}?from=following`}
                  className="block rounded-2xl text-inherit no-underline"
                  draggable={false}
                  onDragStart={(e) => e.preventDefault()}
                >
                  <ListingCard
                    addressLine1={addressLine1}
                    addressLine2={addressLine2}
                    imageUrl={imageUrl}
                    imageAlt={imageAlt}
                    rows={detailRows}
                    stackedRows
                    followState={{
                      isFollowed: true,
                      onToggle: (ev) => toggleFollow(r.index, ev),
                    }}
                    unoptimized
                  />
                </Link>
              );
            });
            })()}
          </div>
          </>
        )}
      </div>
    </main>
  );
}
