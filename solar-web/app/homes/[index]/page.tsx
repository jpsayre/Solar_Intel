"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { supabaseBrowser } from "@/lib/supabase/client";
import ListingCard from "@/components/ListingCard";


const BUCKET = "images";

type HomeRow = {
  index: string; // e.g. "BOULDER_CO_1014"
  original_index: number; // e.g. 1014
  [key: string]: any;
};

export default function HomeDetailPage() {
  const router = useRouter();
  const params = useParams<{ index: string }>();

  const [row, setRow] = useState<HomeRow | null>(null);
  const [imgUrl, setImgUrl] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [imgErr, setImgErr] = useState<string | null>(null);

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

  if (err) return <pre style={{ padding: 24 }}>{err}</pre>;
  if (!row) return <p style={{ padding: 24 }}>Loading…</p>;

  return (
    <main style={{ padding: 24 }}>
      <Link href="/homes">← Back</Link>

      <h1 style={{ marginTop: 12 }}>Home {row.index}</h1>
      <div style={{ fontSize: 14, opacity: 0.8 }}>original_index: {row.original_index}</div>

      <div style={{ marginTop: 12, maxWidth: 900 }}>
        {imgUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imgUrl}
            alt={`Home ${row.original_index}`}
            style={{ width: "100%", borderRadius: 12 }}
          />
        ) : (
          <div style={{ padding: 12, border: "1px solid #333", borderRadius: 12 }}>
            <div>No image found for original_index={row.original_index}</div>
            {imgErr && <div style={{ marginTop: 8, opacity: 0.8 }}>Storage error: {imgErr}</div>}
          </div>
        )}
      </div>

      <h2 style={{ marginTop: 18 }}>Data</h2>
      <pre>{JSON.stringify(row, null, 2)}</pre>
    </main>
  );
}
