"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";

const COMMON_TAGS = [
  { key: "roof_condition", label: "Roof Condition" },
  { key: "roofing_material", label: "Roofing Material" },
  { key: "roof_age", label: "Estimated Roof Age" },
  { key: "energy_bill", label: "Electricity Bill (kWh)" },
] as const;

const ROOF_CONDITION_OPTIONS = ["Excellent", "Good", "Fair", "Poor"] as const;

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
  text: string;
  completed: boolean;
  created_at?: string;
};

type ContactRow = {
  phone_number: string;
  email: string;
  preferred_name: string;
  consent_to_contact: boolean;
};

const EMPTY_CONTACT: ContactRow = {
  phone_number: "",
  email: "",
  preferred_name: "",
  consent_to_contact: false,
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
  custom: Record<string, unknown> | null;
  updated_at?: string | null;
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

  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgHome, setOrgHome] = useState<OrgHomeRow | null | "none">(null);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [newActionItemText, setNewActionItemText] = useState("");
  const [showCompletedActionItems, setShowCompletedActionItems] = useState(false);
  const [contacts, setContacts] = useState<ContactRow[]>([{ ...EMPTY_CONTACT }]);
  const [customTags, setCustomTags] = useState<Record<string, string>>({});
  const [customTagKeys, setCustomTagKeys] = useState<string[]>([]);
  const [newCustomKey, setNewCustomKey] = useState("");
  const [newCustomValue, setNewCustomValue] = useState("");
  const [tagsErr, setTagsErr] = useState<string | null>(null);
  const [savingTags, setSavingTags] = useState(false);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextAutoSaveRef = useRef(true);
  const orgHomeRef = useRef(orgHome);
  orgHomeRef.current = orgHome;
  const lastSavedContactsRef = useRef<string | null>(null);
  const lastSavedHomeInfoRef = useRef<string | null>(null);
  const lastSavedCustomTagsRef = useRef<string | null>(null);
  const lastSavedActionItemsRef = useRef<string | null>(null);

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
        setOrgHome("none");
        return;
      }

      setOrgId(profile.org_id as string);

      const { data: orgHomeRow, error } = await supabaseBrowser
        .from("org_home")
        .select("id, org_id, home_index, custom, updated_at")
        .eq("org_id", profile.org_id)
        .eq("home_index", params.index)
        .maybeSingle();

      if (!alive) return;
      if (error) {
        setTagsErr(error.message);
        setOrgHome("none");
        return;
      }

      setOrgHome(orgHomeRow ? (orgHomeRow as OrgHomeRow) : "none");

      const custom = (orgHomeRow as OrgHomeRow | null)?.custom;
      if (custom && typeof custom === "object") {
        const rawContacts = custom.contacts;
        let parsedContacts: ContactRow[] = [{ ...EMPTY_CONTACT }];
        if (Array.isArray(rawContacts) && rawContacts.length > 0) {
          parsedContacts = rawContacts.map((c) => {
            if (c && typeof c === "object") {
              return {
                phone_number: typeof c.phone_number === "string" ? c.phone_number : "",
                email: typeof c.email === "string" ? c.email : "",
                preferred_name: typeof c.preferred_name === "string" ? c.preferred_name : "",
                consent_to_contact: Boolean(c.consent_to_contact),
              };
            }
            return { ...EMPTY_CONTACT };
          });
          setContacts(parsedContacts);
        } else {
          setContacts(parsedContacts);
        }

        const rawActionItems = custom.action_items;
        if (Array.isArray(rawActionItems)) {
          const parsed: ActionItem[] = rawActionItems
            .filter((a): a is Record<string, unknown> => a != null && typeof a === "object")
            .map((a) => ({
              id: typeof a.id === "string" ? a.id : String(Date.now() + Math.random()),
              text: typeof a.text === "string" ? a.text : "",
              completed: Boolean(a.completed),
              created_at: typeof a.created_at === "string" ? a.created_at : undefined,
            }))
            .filter((a) => a.text !== "" || a.completed);
          setActionItems(parsed);
          lastSavedActionItemsRef.current = JSON.stringify(parsed);
        } else {
          setActionItems([]);
          lastSavedActionItemsRef.current = null;
        }

        const entries: Record<string, string> = {};
        const knownKeys = new Set<string>(COMMON_TAGS.map((t) => t.key));
        const skipKeys = new Set(["contacts", "action_items", "phone_number", "email", "contact_info_updated_at", "home_info_updated_at", "custom_tags_updated_at", "action_items_updated_at"]);
        const customKeys: string[] = [];
        for (const [k, v] of Object.entries(custom)) {
          if (skipKeys.has(k)) continue;
          if (typeof k === "string" && (v === null || typeof v === "string" || typeof v === "number")) {
            entries[k] = String(v);
            if (!knownKeys.has(k)) customKeys.push(k);
          }
        }
        setCustomTags(entries);
        setCustomTagKeys(customKeys.sort((a, b) => a.localeCompare(b)));

        lastSavedContactsRef.current = JSON.stringify(
          parsedContacts.map((c) => ({
            phone_number: c.phone_number.trim(),
            email: c.email.trim(),
            preferred_name: c.preferred_name.trim(),
            consent_to_contact: c.consent_to_contact,
          }))
        );
        const homeInfo: Record<string, string> = {};
        for (const t of COMMON_TAGS) {
          const val = entries[t.key];
          if (val != null && val.trim() !== "") homeInfo[t.key] = val.trim();
        }
        lastSavedHomeInfoRef.current = JSON.stringify(homeInfo);
        const customOnly: Record<string, string> = {};
        for (const k of customKeys) {
          const val = entries[k];
          if (val != null && val.trim() !== "") customOnly[k] = val.trim();
        }
        lastSavedCustomTagsRef.current = JSON.stringify(customOnly);
      } else {
        setContacts([{ ...EMPTY_CONTACT }]);
        setActionItems([]);
        setCustomTags({});
        setCustomTagKeys([]);
        lastSavedContactsRef.current = null;
        lastSavedHomeInfoRef.current = null;
        lastSavedCustomTagsRef.current = null;
        lastSavedActionItemsRef.current = null;
      }
    }

    loadOrgHome();
    return () => {
      alive = false;
    };
  }, [params.index]);

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

  function setContactField(i: number, field: keyof ContactRow, value: string | boolean) {
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
    setContacts((prev) => (prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i)));
  }

  function addActionItem() {
    const text = newActionItemText.trim();
    if (!text) return;
    const id = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `item-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setActionItems((prev) => [...prev, { id, text, completed: false, created_at: new Date().toISOString() }]);
    setNewActionItemText("");
  }

  function removeActionItem(id: string) {
    setActionItems((prev) => prev.filter((a) => a.id !== id));
  }

  function toggleActionItem(id: string) {
    setActionItems((prev) => prev.map((a) => (a.id === id ? { ...a, completed: !a.completed } : a)));
  }

  function setTagValue(key: string, value: string) {
    setCustomTags((prev) => ({ ...prev, [key]: value }));
  }

  function addCustomTag() {
    const key = newCustomKey.trim().toLowerCase().replace(/\s+/g, "_");
    if (!key || customTagKeys.includes(key) || COMMON_TAGS.some((t) => t.key === key)) return;
    setCustomTagKeys((prev) => [...prev, key].sort((a, b) => a.localeCompare(b)));
    setCustomTags((prev) => ({ ...prev, [key]: newCustomValue.trim() }));
    setNewCustomKey("");
    setNewCustomValue("");
  }

  function removeCustomTag(key: string) {
    setCustomTagKeys((prev) => prev.filter((k) => k !== key));
    setCustomTags((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const saveOrgHomeInfo = useCallback(async () => {
    if (!orgId || !params.index) return;
    const { data: userData } = await supabaseBrowser.auth.getUser();
    if (!userData.user) return;

    setSavingTags(true);
    setTagsErr(null);

    const contactsPayload = contacts.map((c) => ({
      phone_number: c.phone_number.trim(),
      email: c.email.trim(),
      preferred_name: c.preferred_name.trim(),
      consent_to_contact: c.consent_to_contact,
    }));

    const actionItemsPayload = actionItems.map((a) => ({
      id: a.id,
      text: a.text,
      completed: a.completed,
      created_at: a.created_at,
    }));

    const homeInfoPayload: Record<string, string> = {};
    for (const t of COMMON_TAGS) {
      const v = customTags[t.key];
      if (v != null && String(v).trim() !== "") homeInfoPayload[t.key] = String(v).trim();
    }

    const customTagsPayload: Record<string, string> = {};
    for (const k of customTagKeys) {
      const v = customTags[k];
      if (v != null && String(v).trim() !== "") customTagsPayload[k] = String(v).trim();
    }

    const contactsSerialized = JSON.stringify(contactsPayload);
    const homeInfoSerialized = JSON.stringify(homeInfoPayload);
    const customTagsSerialized = JSON.stringify(customTagsPayload);
    const actionItemsSerialized = JSON.stringify(actionItemsPayload);

    const contactInfoChanged = lastSavedContactsRef.current !== contactsSerialized;
    const homeInfoChanged = lastSavedHomeInfoRef.current !== homeInfoSerialized;
    const customTagsChanged = lastSavedCustomTagsRef.current !== customTagsSerialized;
    const actionItemsChanged = lastSavedActionItemsRef.current !== actionItemsSerialized;

    const now = new Date().toISOString();
    const currentOrgHome = orgHomeRef.current;
    const existingCustom =
      currentOrgHome !== null && currentOrgHome !== "none" && typeof currentOrgHome === "object" && currentOrgHome.custom && typeof currentOrgHome.custom === "object"
        ? { ...(currentOrgHome.custom as Record<string, unknown>) }
        : {};

    const customPayload: Record<string, unknown> = { ...existingCustom, contacts: contactsPayload, action_items: actionItemsPayload };
    for (const [k, v] of Object.entries(homeInfoPayload)) customPayload[k] = v;
    for (const [k, v] of Object.entries(customTagsPayload)) customPayload[k] = v;

    if (contactInfoChanged) customPayload.contact_info_updated_at = now;
    if (homeInfoChanged) customPayload.home_info_updated_at = now;
    if (customTagsChanged) customPayload.custom_tags_updated_at = now;
    if (actionItemsChanged) customPayload.action_items_updated_at = now;

    let saveError: string | null = null;
    if (currentOrgHome !== null && currentOrgHome !== "none" && typeof currentOrgHome === "object") {
      const { error } = await supabaseBrowser
        .from("org_home")
        .update({ custom: customPayload })
        .eq("id", currentOrgHome.id);
      if (error) {
        setTagsErr(error.message);
        saveError = error.message;
      }
    } else {
      const { error } = await supabaseBrowser.from("org_home").insert({
        org_id: orgId,
        home_index: params.index,
        created_by: userData.user.id,
        custom: customPayload,
      });
      if (error) {
        setTagsErr(error.message);
        saveError = error.message;
      }
    }

    setSavingTags(false);
    if (!saveError) {
      lastSavedContactsRef.current = contactsSerialized;
      lastSavedHomeInfoRef.current = homeInfoSerialized;
      lastSavedCustomTagsRef.current = customTagsSerialized;
      lastSavedActionItemsRef.current = actionItemsSerialized;
      const { data } = await supabaseBrowser
        .from("org_home")
        .select("id, org_id, home_index, custom, updated_at")
        .eq("org_id", orgId)
        .eq("home_index", params.index)
        .single();
      if (data) setOrgHome(data as OrgHomeRow);
    }
  }, [contacts, actionItems, customTags, customTagKeys, orgId, params.index]);

  useEffect(() => {
    if (!orgId || !params.index) return;
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
  }, [contacts, actionItems, customTags, customTagKeys, orgId, params.index, saveOrgHomeInfo]);

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

  const custom = orgHome !== null && orgHome !== "none" && typeof orgHome === "object" && orgHome.custom && typeof orgHome.custom === "object" ? (orgHome.custom as Record<string, unknown>) : null;
  const contactInfoUpdatedText = custom?.contact_info_updated_at && typeof custom.contact_info_updated_at === "string" ? formatNoteTimestamp(custom.contact_info_updated_at) : null;
  const homeInfoUpdatedText = custom?.home_info_updated_at && typeof custom.home_info_updated_at === "string" ? formatNoteTimestamp(custom.home_info_updated_at) : null;
  const customTagsUpdatedText = custom?.custom_tags_updated_at && typeof custom.custom_tags_updated_at === "string" ? formatNoteTimestamp(custom.custom_tags_updated_at) : null;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-4xl">
        <Link
          href="/homes"
          onClick={(e) => {
            if (typeof window !== "undefined" && window.history.length > 1) {
              e.preventDefault();
              router.back();
            }
          }}
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

        {orgId != null && (
          <section className="mt-10">
            <h2 className="mb-2 text-lg font-semibold text-slate-900">My Organization&apos;s Info</h2>
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
                          checked={false}
                          onChange={() => toggleActionItem(a.id)}
                          className="h-4 w-4 rounded border-neutral-300 text-amber-500 focus:ring-amber-400"
                          aria-label={`Mark "${a.text}" complete`}
                        />
                        <span className="min-w-0 flex-1 text-sm text-slate-800">{a.text}</span>
                        <button
                          type="button"
                          onClick={() => removeActionItem(a.id)}
                          className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                          aria-label={`Remove "${a.text}"`}
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
                                checked={true}
                                onChange={() => toggleActionItem(a.id)}
                                className="h-4 w-4 rounded border-neutral-300 text-amber-500 focus:ring-amber-400"
                                aria-label={`Mark "${a.text}" incomplete`}
                              />
                              <span className="min-w-0 flex-1 text-sm text-slate-500 line-through">{a.text}</span>
                              <button
                                type="button"
                                onClick={() => removeActionItem(a.id)}
                                className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                                aria-label={`Remove "${a.text}"`}
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
                <div className="mb-3 flex items-start justify-between gap-2">
                  <h3 className="text-sm font-medium text-slate-700">Contact Info</h3>
                  {contactInfoUpdatedText && (
                    <span className="shrink-0 text-xs text-slate-500">Last updated: {contactInfoUpdatedText}</span>
                  )}
                </div>
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
                      <label className="flex shrink-0 items-center gap-2 py-2">
                        <input
                          type="checkbox"
                          checked={contact.consent_to_contact}
                          onChange={(e) => setContactField(i, "consent_to_contact", e.target.checked)}
                          className="h-4 w-4 rounded border-neutral-300 text-amber-500 focus:ring-amber-400"
                        />
                        <span className="text-xs font-medium text-slate-600">Consent to Contact</span>
                      </label>
                      {contacts.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeContact(i)}
                          className="shrink-0 rounded-lg px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                        >
                          Remove
                        </button>
                      )}
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
              </div>

              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <h3 className="text-sm font-medium text-slate-700">Home Info</h3>
                  {homeInfoUpdatedText && (
                    <span className="shrink-0 text-xs text-slate-500">Last updated: {homeInfoUpdatedText}</span>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {COMMON_TAGS.map(({ key, label }) => (
                    <label key={key} className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-500">{label}</span>
                      {key === "roof_condition" ? (
                        <select
                          value={customTags[key] ?? ""}
                          onChange={(e) => setTagValue(key, e.target.value)}
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
                          value={customTags[key] ?? ""}
                          onChange={(e) => setTagValue(key, e.target.value)}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        >
                          <option value="">Select…</option>
                          {ROOFING_MATERIAL_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={customTags[key] ?? ""}
                          onChange={(e) => setTagValue(key, e.target.value)}
                          placeholder={label}
                          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                        />
                      )}
                    </label>
                  ))}
                </div>
              </div>

              {customTagKeys.length > 0 && (
                <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4">
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <h3 className="text-sm font-medium text-slate-700">Custom Tags</h3>
                    {customTagsUpdatedText && (
                      <span className="shrink-0 text-xs text-slate-500">Last updated: {customTagsUpdatedText}</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {customTagKeys.map((key) => {
                      const value = customTags[key] ?? "";
                      return (
                        <span
                          key={key}
                          className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-slate-800"
                        >
                          <span>{key.replace(/_/g, " ")}: {value}</span>
                          <button
                            type="button"
                            onClick={() => removeCustomTag(key)}
                            className="ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-1"
                            aria-label={`Remove ${key}`}
                          >
                            ×
                          </button>
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-500">New Tag Name</span>
                  <input
                    type="text"
                    value={newCustomKey}
                    onChange={(e) => setNewCustomKey(e.target.value)}
                    placeholder="e.g. competitor_quote"
                    className="w-40 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-500">Value</span>
                  <input
                    type="text"
                    value={newCustomValue}
                    onChange={(e) => setNewCustomValue(e.target.value)}
                    placeholder="Value"
                    className="w-40 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                  />
                </label>
                <button
                  type="button"
                  onClick={addCustomTag}
                  className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
                >
                  Add Custom Tag
                </button>
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
        )}

        {orgId === null && orgHome === "none" && (
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
