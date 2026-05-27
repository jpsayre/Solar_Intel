"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
// import { useState } from "react";
// import { supabaseBrowser } from "@/lib/supabase/client";

export default function Home() {
  const router = useRouter();

  // Public-access mode: always send to /homes. Auth-aware redirect kept below
  // for when login is re-enabled.
  useEffect(() => {
    router.replace("/homes");
  }, [router]);

  // --- Original auth-aware redirect (disabled) ---
  // const [user, setUser] = useState<{ id: string } | null>(null);
  // const [loading, setLoading] = useState(true);
  //
  // useEffect(() => {
  //   supabaseBrowser.auth.getUser().then(({ data }) => {
  //     setUser(data.user ?? null);
  //     setLoading(false);
  //   });
  // }, []);
  //
  // useEffect(() => {
  //   if (loading) return;
  //   if (user) {
  //     router.replace("/homes");
  //   } else {
  //     router.replace("/login");
  //   }
  // }, [loading, user, router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
      <p className="mt-3 text-slate-600">Loading…</p>
    </main>
  );
}
