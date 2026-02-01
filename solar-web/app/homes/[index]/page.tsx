"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { supabaseBrowser } from "@/lib/supabase/client";
import { buildListingCardData } from "@/lib/cardData";
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
      </div>
    </main>
  );
}
