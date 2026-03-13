"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import { indexToImagePath } from "@/lib/imagePath";
import ListingCard from "@/components/ListingCard";
import ReportIssueModal from "@/components/ReportIssueModal";

const BUCKET = "images";

const HOME_INFO_FIELDS = [
  { key: "roof_condition", label: "Roof Condition" },
  { key: "roofing_material", label: "Roofing Material" },
  { key: "energy_bill_kwh", label: "Electricity Bill (kWh)" },
  { key: "interest_in_solar", label: "Interest in Solar" },
  { key: "interest_in_battery", label: "Interest in Battery" },
  { key: "ev_ownership", label: "EV Ownership" },
] as const;

const ROOF_CONDITION_OPTIONS = ["Excellent", "Good", "Fair", "Poor"] as const;
const INTEREST_OPTIONS = ["Unknown", "Cold", "Cool", "Warm", "Hot"] as const;
const EV_OWNERSHIP_OPTIONS = ["Unknown", "Doesn't Want", "Interested", "Owns an EV", "Owns 2+ EVs"] as const;
const ROOFING_MATERIAL_OPTIONS = [
  "Asphalt Shingles",
  "Ceramic Tile",
  "Metal",
  "Wood Shingles",
  "Slate/Stone",
  "Other",
] as const;

type ActionItem = {
  id: string;
  body: string;
  completed: boolean;
  created_at?: string;
  completed_at?: string | null;
};

type ContactRow = {
  id?: number;
  preferred_name: string;
  phone_number: string;
  email: string;
};

const EMPTY_CONTACT: ContactRow = {
  phone_number: "",
  email: "",
  preferred_name: "",
};

type HomeRow = {
  index: string;
  original_index: number;
  [key: string]: unknown;
};

type OrgHomeRow = {
  id: number;
  org_id: string;
  home_index: string;
  tags: string[] | null;
  roof_condition: string | null;
  roofing_material: string | null;
  energy_bill_kwh: number | null;
  interest_in_solar: string | null;
  interest_in_battery: string | null;
  ev_ownership: string | null;
  do_not_contact: boolean;
  updated_at: string;
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

type PermitRow = {
  id: number;
  permit_number: string | null;
  permit_type: string;
  description: string | null;
  filed_date: string;
  valuation: number | null;
};

const PERMIT_TAG_COLORS: Record<string, string> = {
  solar: "bg-amber-100 text-amber-800",
  roof: "bg-blue-100 text-blue-700",
  battery: "bg-green-100 text-green-700",
  ev_charger: "bg-purple-100 text-purple-700",
  electrical: "bg-indigo-100 text-indigo-700",
  heat_pump: "bg-purple-100 text-purple-700",
  hvac: "bg-purple-100 text-purple-700",
  water_heater: "bg-cyan-100 text-cyan-700",
  generator: "bg-orange-100 text-orange-700",
  envelope: "bg-teal-100 text-teal-700",
  pool: "bg-sky-100 text-sky-700",
  remodel: "bg-amber-100 text-amber-700",
  construction: "bg-amber-100 text-amber-700",
  other: "bg-slate-100 text-slate-700",
};

const PERMIT_TYPE_LABELS: Record<string, string> = {
  solar: "Solar",
  roof: "Roof",
  battery: "Battery",
  ev_charger: "EV Charger",
  electrical: "Electrical",
  heat_pump: "Heat Pump",
  hvac: "HVAC",
  water_heater: "Water Heater",
  generator: "Generator",
  envelope: "Energy Efficiency",
  pool: "Pool",
  remodel: "Remodel",
  construction: "Construction",
  other: "Other",
};

export default function HomeDetailPage() {
  const router = useRouter();
  const params = useParams<{ index: string }>();
  const searchParams = useSearchParams();
  const from = searchParams.get("from");
  const backLabel = from === "following" ? "Back to following" : from === "alerts" ? "Back to alerts" : "Back to explorer";
  const backHref = from === "following" ? "/following" : from === "alerts" ? "/alerts" : "/homes";

  useEffect(() => { window.scrollTo(0, 0); }, []);

  const [row, setRow] = useState<HomeRow | null>(null);
  const [imgUrl, setImgUrl] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [imgErr, setImgErr] = useState<string | null>(null);

  const [notes, setNotes] = useState<HomeNote[] | null>(null);
  const [notesErr, setNotesErr] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [userId, setUserId] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgHomeLoaded, setOrgHomeLoaded] = useState(false);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [newActionItemText, setNewActionItemText] = useState("");
  const [showCompletedActionItems, setShowCompletedActionItems] = useState(false);
  const [contacts, setContacts] = useState<ContactRow[]>([{ ...EMPTY_CONTACT }]);
  const [homeInfo, setHomeInfo] = useState<Record<string, string>>({});
  const [tags, setTags] = useState<string[]>([]);
  const [doNotContact, setDoNotContact] = useState(false);
  const [newTagEntry, setNewTagEntry] = useState("");
  const [tagsErr, setTagsErr] = useState<string | null>(null);
  const [savingTags, setSavingTags] = useState(false);
  const [orgHomeUpdatedAt, setOrgHomeUpdatedAt] = useState<string | null>(null);
  const [isFollowed, setIsFollowed] = useState(false);
  const [reportIssueOpen, setReportIssueOpen] = useState(false);
  const [scores, setScores] = useState<{ model_score: number | null; roof_score: number | null } | null>(null);
  const [enrichCredits, setEnrichCredits] = useState(47);
  const [permitsOpen, setPermitsOpen] = useState(false);
  const [permits, setPermits] = useState<PermitRow[]>([]);
  const groupedPermits = useMemo(() => {
    const groups = new Map<string, { ids: number[]; permit_number: string | null; types: string[]; description: string | null; filed_date: string; valuation: number | null }>();
    for (const p of permits) {
      const key = p.permit_number ?? `__id_${p.id}`;
      const existing = groups.get(key);
      if (existing) {
        if (!existing.types.includes(p.permit_type)) existing.types.push(p.permit_type);
        existing.ids.push(p.id);
      } else {
        groups.set(key, { ids: [p.id], permit_number: p.permit_number, types: [p.permit_type], description: p.description, filed_date: p.filed_date, valuation: p.valuation });
      }
    }
    return Array.from(groups.values());
  }, [permits]);
  const [enrichedEmail, setEnrichedEmail] = useState<{ name: string; email: string } | null>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextAutoSaveRef = useRef(true);

  // Load home row, scores, permits, image
  useEffect(() => {
    let alive = true;

    async function load() {
      setErr(null);
      setImgErr(null);
      setImgUrl("");
      setRow(null);

      const { data: userData, error: userErr } = await supabaseBrowser.auth.getUser();
      if (userErr) {
        if (alive) setErr(userErr.message);
        return;
      }
      if (!userData.user) {
        router.push("/login");
        return;
      }
      setUserId(userData.user.id);

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

      const { data: scoreData } = await supabaseBrowser
        .from("home_scores")
        .select("model_score, roof_score")
        .eq("home_index", idx)
        .maybeSingle();
      if (alive && scoreData) {
        setScores({ model_score: scoreData.model_score, roof_score: scoreData.roof_score });
      }

      const { data: permitData } = await supabaseBrowser
        .from("permits")
        .select("id, permit_number, permit_type, description, filed_date, valuation")
        .eq("home_index", idx)
        .order("filed_date", { ascending: false });
      if (alive && permitData) {
        setPermits(permitData as PermitRow[]);
      }

      const path = indexToImagePath((data as HomeRow).index);
      const { data: urlData } = supabaseBrowser.storage
        .from(BUCKET)
        .getPublicUrl(path);

      if (!alive) return;

      setImgUrl(urlData?.publicUrl ?? "");
    }

    load();
    return () => { alive = false; };
  }, [params.index, router]);

  // Load follow state
  useEffect(() => {
    let alive = true;
    async function loadFollowState() {
      const idx = params.index;
      if (!idx) return;
      const { data: userData } = await supabaseBrowser.auth.getUser();
      if (!userData.user || !alive) {
        if (alive) setIsFollowed(false);
        return;
      }
      const { data } = await supabaseBrowser
        .from("user_follows")
        .select("home_index")
        .eq("user_id", userData.user.id)
        .eq("home_index", idx)
        .maybeSingle();
      if (alive) setIsFollowed(!!data);
    }
    loadFollowState();
    return () => { alive = false; };
  }, [params.index]);

  const toggleFollow = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      const idx = params.index;
      if (!idx) return;
      const { data: userData } = await supabaseBrowser.auth.getUser();
      if (!userData.user) return;
      if (isFollowed) {
        await supabaseBrowser.from("user_follows").delete().eq("user_id", userData.user.id).eq("home_index", idx);
        setIsFollowed(false);
      } else {
        await supabaseBrowser.from("user_follows").insert({ user_id: userData.user.id, home_index: idx });
        setIsFollowed(true);
      }
    },
    [params.index, isFollowed]
  );

  // Load notes
  const loadNotes = useCallback(async () => {
    const idx = params.index;
    if (!idx) return;
    setNotesErr(null);
    setNotes(null);
    const { data, error } = await supabaseBrowser
      .from("org_home_comments")
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
    loadNotes().then(() => { if (!alive) return; });
    return () => { alive = false; };
  }, [row, params.index, loadNotes]);

  // Load org_home + contacts + action items from separate tables
  useEffect(() => {
    let alive = true;

    async function loadOrgHome() {
      const { data: userData } = await supabaseBrowser.auth.getUser();
      if (!userData.user || !params.index) return;

      const { data: profile } = await supabaseBrowser
        .from("profiles")
        .select("org_id")
        .eq("user_id", userData.user.id)
        .single();

      if (!alive || !profile?.org_id) {
        setOrgId(null);
        setOrgHomeLoaded(true);
        return;
      }

      const currentOrgId = profile.org_id as string;
      setOrgId(currentOrgId);

      // Load org_home row (scalar fields + tags)
      const { data: ohRow } = await supabaseBrowser
        .from("org_home")
        .select("*")
        .eq("org_id", currentOrgId)
        .eq("home_index", params.index)
        .maybeSingle();

      if (!alive) return;

      if (ohRow) {
        const oh = ohRow as OrgHomeRow;
        setTags(oh.tags ?? []);
        setDoNotContact(oh.do_not_contact ?? false);
        setHomeInfo({
          roof_condition: oh.roof_condition ?? "",
          roofing_material: oh.roofing_material ?? "",
          energy_bill_kwh: oh.energy_bill_kwh != null ? String(oh.energy_bill_kwh) : "",
          interest_in_solar: oh.interest_in_solar ?? "",
          interest_in_battery: oh.interest_in_battery ?? "",
          ev_ownership: oh.ev_ownership ?? "",
        });
        setOrgHomeUpdatedAt(oh.updated_at);
      } else {
        setTags([]);
        setDoNotContact(false);
        setHomeInfo({});
        setOrgHomeUpdatedAt(null);
      }

      // Load contacts
      const { data: contactsData } = await supabaseBrowser
        .from("org_home_contacts")
        .select("id, preferred_name, phone_number, email")
        .eq("org_id", currentOrgId)
        .eq("home_index", params.index)
        .order("id");

      if (!alive) return;

      if (contactsData && contactsData.length > 0) {
        setContacts(contactsData.map((c) => ({
          id: c.id as number,
          preferred_name: (c.preferred_name as string) ?? "",
          phone_number: (c.phone_number as string) ?? "",
          email: (c.email as string) ?? "",
        })));
      } else {
        setContacts([{ ...EMPTY_CONTACT }]);
      }

      // Load action items
      const { data: aiData } = await supabaseBrowser
        .from("org_home_action_items")
        .select("id, body, completed, created_by, created_at, completed_at")
        .eq("org_id", currentOrgId)
        .eq("home_index", params.index)
        .order("created_at");

      if (!alive) return;

      if (aiData && aiData.length > 0) {
        setActionItems(aiData.map((a) => ({
          id: a.id as string,
          body: (a.body as string) ?? "",
          completed: Boolean(a.completed),
          created_at: a.created_at as string | undefined,
          completed_at: a.completed_at as string | null | undefined,
        })));
      } else {
        setActionItems([]);
      }

      setOrgHomeLoaded(true);
    }

    loadOrgHome();
    return () => { alive = false; };
  }, [params.index]);

  // Add note (includes org_id)
  async function handleAddNote(e: React.FormEvent) {
    e.preventDefault();
    const body = noteBody.trim();
    if (!body || !params.index) return;
    const { data: userData } = await supabaseBrowser.auth.getUser();
    if (!userData.user) return;
    setSubmitting(true);
    setNotesErr(null);
    const { error } = await supabaseBrowser.from("org_home_comments").insert({
      home_index: params.index,
      author_id: userData.user.id,
      org_id: orgId,
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

  function setContactField(i: number, field: keyof ContactRow, value: string) {
    setContacts((prev) => {
      const next = [...prev];
      if (i < 0 || i >= next.length) return prev;
      next[i] = { ...next[i], [field]: value };
      return next;
    });
  }

  function addContact() {
    setContacts((prev) => [...prev, { ...EMPTY_CONTACT }]);
  }

  function removeContact(i: number) {
    setContacts((prev) => (prev.length <= 1 ? [{ ...EMPTY_CONTACT }] : prev.filter((_, idx) => idx !== i)));
  }

  function addActionItem() {
    const text = newActionItemText.trim();
    if (!text) return;
    const id = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `item-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setActionItems((prev) => [...prev, { id, body: text, completed: false, created_at: new Date().toISOString() }]);
    setNewActionItemText("");
  }

  function removeActionItem(id: string) {
    setActionItems((prev) => prev.filter((a) => a.id !== id));
  }

  function toggleActionItem(id: string) {
    setActionItems((prev) => prev.map((a) => {
      if (a.id !== id) return a;
      const nowCompleted = !a.completed;
      return { ...a, completed: nowCompleted, completed_at: nowCompleted ? new Date().toISOString() : null };
    }));
  }

  function setHomeInfoValue(key: string, value: string) {
    setHomeInfo((prev) => ({ ...prev, [key]: value }));
  }

  function addTag() {
    const tag = newTagEntry.trim();
    if (!tag || tags.includes(tag)) return;
    setTags((prev) => [...prev, tag].sort((a, b) => a.localeCompare(b)));
    setNewTagEntry("");
  }

  function removeTag(tag: string) {
    setTags((prev) => prev.filter((t) => t !== tag));
  }

  // Save to org_home (upsert), org_home_contacts (replace), org_home_action_items (replace)
  const saveOrgHomeInfo = useCallback(async () => {
    if (!orgId || !params.index || !userId) return;

    setSavingTags(true);
    setTagsErr(null);

    let saveError: string | null = null;

    // 1. Upsert org_home scalar fields + tags
    const orgHomePayload: Record<string, unknown> = {
      org_id: orgId,
      home_index: params.index,
      tags,
      do_not_contact: doNotContact,
      roof_condition: homeInfo.roof_condition || null,
      roofing_material: homeInfo.roofing_material || null,
      energy_bill_kwh: homeInfo.energy_bill_kwh ? parseFloat(homeInfo.energy_bill_kwh) : null,
      interest_in_solar: homeInfo.interest_in_solar || null,
      interest_in_battery: homeInfo.interest_in_battery || null,
      ev_ownership: homeInfo.ev_ownership || null,
      created_by: userId,
    };

    const { data: upsertedRow, error: ohErr } = await supabaseBrowser
      .from("org_home")
      .upsert(orgHomePayload, { onConflict: "org_id,home_index" })
      .select("updated_at")
      .single();

    if (ohErr) {
      setTagsErr(ohErr.message);
      saveError = ohErr.message;
    } else if (upsertedRow) {
      setOrgHomeUpdatedAt(upsertedRow.updated_at as string);
    }

    // 2. Replace contacts
    if (!saveError) {
      await supabaseBrowser
        .from("org_home_contacts")
        .delete()
        .eq("org_id", orgId)
        .eq("home_index", params.index);

      const nonEmpty = contacts.filter(
        (c) => c.preferred_name.trim() || c.phone_number.trim() || c.email.trim()
      );
      if (nonEmpty.length > 0) {
        const { error: cErr } = await supabaseBrowser
          .from("org_home_contacts")
          .insert(
            nonEmpty.map((c) => ({
              org_id: orgId,
              home_index: params.index,
              preferred_name: c.preferred_name.trim(),
              phone_number: c.phone_number.trim(),
              email: c.email.trim(),
            }))
          );
        if (cErr) {
          setTagsErr(cErr.message);
          saveError = cErr.message;
        }
      }
    }

    // 3. Replace action items
    if (!saveError) {
      await supabaseBrowser
        .from("org_home_action_items")
        .delete()
        .eq("org_id", orgId)
        .eq("home_index", params.index);

      if (actionItems.length > 0) {
        const { error: aiErr } = await supabaseBrowser
          .from("org_home_action_items")
          .insert(
            actionItems.map((a) => ({
              id: a.id,
              org_id: orgId,
              home_index: params.index,
              body: a.body,
              completed: a.completed,
              created_by: userId,
              created_at: a.created_at || new Date().toISOString(),
              completed_at: a.completed ? (a.completed_at || new Date().toISOString()) : null,
            }))
          );
        if (aiErr) {
          setTagsErr(aiErr.message);
          saveError = aiErr.message;
        }
      }
    }

    setSavingTags(false);
  }, [contacts, actionItems, homeInfo, tags, doNotContact, orgId, params.index, userId]);

  // Debounced auto-save
  useEffect(() => {
    if (!orgId || !params.index || !orgHomeLoaded) return;
    if (skipNextAutoSaveRef.current) {
      skipNextAutoSaveRef.current = false;
      return;
    }
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      saveTimeoutRef.current = null;
      saveOrgHomeInfo();
    }, 700);
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = null;
      }
    };
  }, [contacts, actionItems, homeInfo, tags, doNotContact, orgId, params.index, orgHomeLoaded, saveOrgHomeInfo]);

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

  const rowWithScores = scores
    ? { ...row, model_score: scores.model_score, roof_score: scores.roof_score }
    : row;
  const { addressLine1, addressLine2, detailRows } = buildListingCardData(rowWithScores);

  const updatedAtText = orgHomeUpdatedAt ? formatNoteTimestamp(orgHomeUpdatedAt) : null;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              if (window.history.length > 1) {
                router.back();
              } else {
                router.push(backHref);
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            ← {backLabel}
          </button>
          <button
            type="button"
            onClick={() => setReportIssueOpen(true)}
            className="text-xs text-slate-400 underline hover:text-slate-600"
          >
            Report an issue
          </button>
        </div>

        <ListingCard
          addressLine1={addressLine1}
          addressLine2={addressLine2}
          imageUrl={imgUrl || "/window.svg"}
          imageAlt={imgUrl ? `Home ${row.original_index}` : imgErr ? "No image" : "Loading…"}
          rows={detailRows}
          followState={{
            isFollowed,
            onToggle: toggleFollow,
          }}
          priority
          unoptimized
          badge={row.has_solar ? "Has Solar" : undefined}
        />

        {reportIssueOpen && (
          <ReportIssueModal
            homeIndex={row.index}
            onClose={() => setReportIssueOpen(false)}
          />
        )}

        <section className="mt-6 rounded-xl border border-neutral-200 bg-white">
          <button
            type="button"
            onClick={() => setPermitsOpen((v) => !v)}
            className="flex w-full items-center justify-between px-5 py-4 text-left focus:outline-none"
          >
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">Permit History</h2>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-600">
                {groupedPermits.length}
              </span>
            </div>
            <svg
              className={`h-5 w-5 text-slate-400 transition-transform ${permitsOpen ? "rotate-180" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {permitsOpen && (
            <div className="border-t border-neutral-200 px-5 pb-4 pt-3">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-neutral-100 text-left text-xs font-medium uppercase tracking-wider text-slate-500">
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4">Permit #</th>
                      <th className="pb-2 pr-4">Type</th>
                      <th className="pb-2 pr-4">Description</th>
                      <th className="pb-2 text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedPermits.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-4 text-center text-sm text-slate-400">No permits on file</td>
                      </tr>
                    ) : groupedPermits.map((g) => {
                      const dateFormatted = g.filed_date ? (() => { const [y, m, d] = g.filed_date.split("-"); return `${parseInt(m)}/${parseInt(d)}/${y}`; })() : "N/A";
                      return (
                      <tr key={g.ids[0]} className="border-b border-neutral-50">
                        <td className="whitespace-nowrap py-2 pr-4 text-slate-600">{dateFormatted}</td>
                        <td className="whitespace-nowrap py-2 pr-4 text-slate-500 text-xs">{g.permit_number ?? "—"}</td>
                        <td className="py-2 pr-4">
                          <div className="flex flex-wrap gap-1">
                            {g.types.map((t) => (
                              <span key={t} className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${PERMIT_TAG_COLORS[t] ?? PERMIT_TAG_COLORS.other}`}>
                                {PERMIT_TYPE_LABELS[t] ?? t}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-2 pr-4 text-slate-700">{g.description ?? "—"}</td>
                        <td className="whitespace-nowrap py-2 text-right text-slate-600">
                          {g.valuation != null ? `$${g.valuation.toLocaleString()}` : "—"}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        <section className="mt-6 rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/50 p-5">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-900">Email Enrichment</h2>
            <span className="rounded-full bg-amber-200 px-2.5 py-0.5 text-xs font-semibold text-amber-800">UNDER DEVELOPMENT</span>
          </div>
          <p className="mb-2 text-sm text-slate-500">
            Look up emails for this property. Credits remaining: <span className="font-semibold text-slate-700">{enrichCredits}</span>
          </p>
          <p className="mb-4 text-xs text-slate-400">
            Demo only — data shown is not real.
          </p>
          {enrichedEmail ? (
            <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wider text-neutral-500">Email match</div>
              <div className="mt-1 text-sm font-semibold text-neutral-900">{enrichedEmail.name}</div>
              <div className="text-sm text-slate-600">{enrichedEmail.email}</div>
            </div>
          ) : (
            <button
              type="button"
              disabled={enrichCredits <= 0}
              onClick={() => {
                const owner = row.owner_1 ? String(row.owner_1).trim() : "J. Smith";
                const parts = owner.toLowerCase().split(/\s+/);
                const first = parts[0] || "john";
                const last = parts[parts.length - 1] || "smith";
                const fakeDomain = "example.com";
                setEnrichedEmail({
                  name: owner,
                  email: `${first}.${last}@${fakeDomain}`,
                });
                setEnrichCredits((c) => Math.max(0, c - 1));
              }}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
            >
              Enrich with email (1 credit)
            </button>
          )}
        </section>

        {orgId != null && (<>
          <section className="mt-10">
            <div className="mb-2 flex items-start justify-between gap-2">
              <h2 className="text-lg font-semibold text-slate-900">My Organization&apos;s Info</h2>
              {updatedAtText && (
                <span className="shrink-0 text-xs text-slate-500">Last updated: {updatedAtText}</span>
              )}
            </div>
            <p className="mb-4 text-sm text-slate-500">
              Action items, contact info, home info, and tags are private to your organization.
            </p>

            <div className="space-y-6">
              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-700">Action Items</h3>
                <ul className="space-y-2">
                  {actionItems
                    .filter((a) => !a.completed)
                    .map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2"
                      >
                        <input
                          type="checkbox"
                          checked={a.completed}
                          onChange={() => toggleActionItem(a.id)}
                          className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                          aria-label={`Mark "${a.body}" complete`}
                        />
                        <span className="min-w-0 flex-1 text-sm text-slate-800">{a.body}</span>
                        <button
                          type="button"
                          onClick={() => removeActionItem(a.id)}
                          className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                          aria-label={`Remove "${a.body}"`}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                </ul>
                <div className="mt-3 flex gap-2">
                  <input
                    type="text"
                    value={newActionItemText}
                    onChange={(e) => setNewActionItemText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addActionItem())}
                    placeholder="Add action item…"
                    className="min-w-0 flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                  />
                  <button
                    type="button"
                    onClick={addActionItem}
                    disabled={!newActionItemText.trim()}
                    className="shrink-0 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-neutral-50 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
                  >
                    Add
                  </button>
                </div>
                {actionItems.some((a) => a.completed) && (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => setShowCompletedActionItems((prev) => !prev)}
                      className="text-xs font-medium text-slate-500 hover:text-slate-700"
                    >
                      {showCompletedActionItems ? "Hide" : "Show"} {actionItems.filter((a) => a.completed).length} completed
                    </button>
                    {showCompletedActionItems && (
                      <ul className="mt-2 space-y-2">
                        {actionItems
                          .filter((a) => a.completed)
                          .map((a) => (
                            <li
                              key={a.id}
                              className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2"
                            >
                              <input
                                type="checkbox"
                                checked={a.completed}
                                onChange={() => toggleActionItem(a.id)}
                                className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                                aria-label={`Mark "${a.body}" incomplete`}
                              />
                              <span className="min-w-0 flex-1 text-sm text-slate-500 line-through">{a.body}</span>
                              <button
                                type="button"
                                onClick={() => removeActionItem(a.id)}
                                className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                                aria-label={`Remove "${a.body}"`}
                              >
                                ×
                              </button>
                            </li>
                          ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-700">Contact Info</h3>
                <div className="space-y-4">
                  {contacts.map((contact, i) => (
                    <div
                      key={i}
                      className="flex flex-wrap items-end gap-3 rounded-lg border border-neutral-200 bg-white p-3"
                    >
                      <label className="min-w-[120px] flex-1 flex-col gap-1 sm:min-w-0">
                        <span className="text-xs font-medium text-slate-500">Phone Number</span>
                        <input
                          type="text"
                          value={contact.phone_number}
                          onChange={(e) => setContactField(i, "phone_number", e.target.value)}
                          placeholder="Phone"
                          className="mt-0.5 w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        />
                      </label>
                      <label className="min-w-[120px] flex-1 flex-col gap-1 sm:min-w-0">
                        <span className="text-xs font-medium text-slate-500">Email</span>
                        <input
                          type="email"
                          value={contact.email}
                          onChange={(e) => setContactField(i, "email", e.target.value)}
                          placeholder="Email"
                          className="mt-0.5 w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        />
                      </label>
                      <label className="min-w-[120px] flex-1 flex-col gap-1 sm:min-w-0">
                        <span className="text-xs font-medium text-slate-500">Preferred Name</span>
                        <input
                          type="text"
                          value={contact.preferred_name}
                          onChange={(e) => setContactField(i, "preferred_name", e.target.value)}
                          placeholder="Name"
                          className="mt-0.5 w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => removeContact(i)}
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-red-600"
                        aria-label="Remove contact"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={addContact}
                  className="mt-3 flex items-center gap-1.5 rounded-lg border border-dashed border-neutral-300 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:border-amber-400 hover:text-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
                >
                  <span className="text-base leading-none">+</span>
                  Add Another Contact
                </button>
                <div className="mt-3 flex justify-end">
                  <label
                    className={`flex cursor-pointer items-center gap-2 py-2 ${doNotContact ? "text-red-600" : "text-slate-500"}`}
                  >
                    <input
                      type="checkbox"
                      checked={doNotContact}
                      onChange={(e) => setDoNotContact(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-300 accent-slate-500 focus:ring-slate-400"
                    />
                    <span className="text-sm font-medium">Do not contact home</span>
                  </label>
                </div>
              </div>

              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-700">Home Info</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  {HOME_INFO_FIELDS.map(({ key, label }) => (
                    <label key={key} className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-500">{label}</span>
                      {key === "roof_condition" ? (
                        <select
                          value={homeInfo[key] ?? ""}
                          onChange={(e) => setHomeInfoValue(key, e.target.value)}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        >
                          <option value="">Select…</option>
                          {ROOF_CONDITION_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : key === "roofing_material" ? (
                        <select
                          value={homeInfo[key] ?? ""}
                          onChange={(e) => setHomeInfoValue(key, e.target.value)}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        >
                          <option value="">Select…</option>
                          {ROOFING_MATERIAL_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : key === "interest_in_solar" || key === "interest_in_battery" ? (
                        <select
                          value={homeInfo[key] ?? ""}
                          onChange={(e) => setHomeInfoValue(key, e.target.value)}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        >
                          <option value="">Select…</option>
                          {INTEREST_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : key === "ev_ownership" ? (
                        <select
                          value={homeInfo[key] ?? ""}
                          onChange={(e) => setHomeInfoValue(key, e.target.value)}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        >
                          <option value="">Select…</option>
                          {EV_OWNERSHIP_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={homeInfo[key] ?? ""}
                          onChange={(e) => setHomeInfoValue(key, e.target.value)}
                          placeholder={label}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        />
                      )}
                    </label>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-700">Tags</h3>
                {tags.length > 0 && (
                  <div className="mb-3 flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-slate-800"
                      >
                        <span>{tag}</span>
                        <button
                          type="button"
                          onClick={() => removeTag(tag)}
                          className="ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-1"
                          aria-label={`Remove ${tag}`}
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-slate-500">Add tag</span>
                    <input
                      type="text"
                      value={newTagEntry}
                      onChange={(e) => setNewTagEntry(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                      placeholder="e.g. hot-lead, callback"
                      className="w-48 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={addTag}
                    disabled={!newTagEntry.trim() || tags.includes(newTagEntry.trim())}
                    className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 disabled:opacity-50 disabled:hover:bg-white"
                  >
                    Add tag
                  </button>
                </div>
              </div>

              {tagsErr && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
                  {tagsErr}
                </div>
              )}

              {savingTags && (
                <p className="text-sm text-slate-500">Saving…</p>
              )}
            </div>
          </section>

          <div className="mt-6 rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/50 px-5 py-4 text-center text-sm text-amber-800">
            Document storage under development
          </div>
        </>)}

        {orgId === null && orgHomeLoaded && (
          <div className="mt-10 rounded-xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
            <p className="font-medium">My Organization&apos;s Info is only shown for users in an organization.</p>
            <p className="mt-1 text-amber-800">
              Your account needs a row in <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs">profiles</code> with your <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs">user_id</code> and an <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs">org_id</code>. Ask your admin to add you to an org, or in Supabase run: <code className="mt-2 block rounded bg-amber-100 p-2 font-mono text-xs">INSERT INTO profiles (user_id, org_id) VALUES (&#39;your-auth-user-uuid&#39;, &#39;your-org-uuid&#39;);</code>
            </p>
          </div>
        )}

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
