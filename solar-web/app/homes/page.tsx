"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";
import ListingCard from "@/components/ListingCard";

const BUCKET = "images";
const PAGE_SIZE = 25;

type HomeRow = {
  index: string; // e.g. "BOULDER_CO_1014"
  original_index: number; // e.g. 1014
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

      // 2) Fetch rows (only needed columns)
      const { data, error } = await supabaseBrowser
        .from("homes")
        .select("index, original_index")
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

  if (err) return <pre style={{ padding: 24 }}>{err}</pre>;
  if (rows === null) return <p style={{ padding: 24 }}>Loading…</p>;

  return (
    <main style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Homes</h1>
        <button
          onClick={async () => {
            await supabaseBrowser.auth.signOut();
            router.push("/login");
          }}
          style={{ padding: "8px 12px" }}
        >
          Logout
        </button>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {rows.map((r) => {
          const url = imgUrls[r.original_index];
          const e = imgErrors[r.original_index];

          return (
            <Link
              key={r.index}
              href={`/homes/${encodeURIComponent(r.index)}`}
              style={{
                display: "flex",
                gap: 12,
                alignItems: "center",
                padding: 12,
                border: "1px solid #333",
                borderRadius: 12,
                textDecoration: "none",
                color: "inherit",
              }}
            >
              <div
                style={{
                  width: 160,
                  height: 90,
                  background: "#111",
                  borderRadius: 10,
                  overflow: "hidden",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flex: "0 0 auto",
                }}
              >
                {url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt={`Home ${r.original_index}`}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  <span style={{ opacity: 0.7, fontSize: 12 }}>{e ? "No access / not found" : "Loading…"}</span>
                )}
              </div>

              <div>
                <div style={{ fontSize: 14, opacity: 0.8 }}>index: {r.index}</div>
                <div style={{ fontSize: 20, fontWeight: 700 }}>original_index: {r.original_index}</div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>Click for details</div>
              </div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
