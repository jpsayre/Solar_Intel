"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
// import { useRouter } from "next/navigation";
// import { supabaseBrowser } from "@/lib/supabase/client";

export default function SiteHeader() {
  const pathname = usePathname();
  // const router = useRouter();
  // const [user, setUser] = useState<{ id: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const menuRef = useRef<HTMLElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setMounted(true);
    // Public-access mode: skip auth state subscription.
    // supabaseBrowser.auth.getUser().then(({ data }) => setUser(data.user ?? null));
    // const { data: { subscription } } = supabaseBrowser.auth.onAuthStateChange(() => {
    //   supabaseBrowser.auth.getUser().then(({ data }) => setUser(data.user ?? null));
    // });
    // return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClickOutside(ev: MouseEvent) {
      const target = ev.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setMenuOpen(false);
    }
    document.addEventListener("click", handleClickOutside, true);
    return () => document.removeEventListener("click", handleClickOutside, true);
  }, [menuOpen]);

  // async function handleLogout() {
  //   setMenuOpen(false);
  //   await supabaseBrowser.auth.signOut();
  //   router.push("/login");
  //   router.refresh();
  // }

  if (!mounted) return null;

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-slate-200/80 bg-white px-4 py-3 sm:px-6">
      <Link
        href="/homes"
        className="text-lg font-bold tracking-tight text-slate-900 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 rounded"
      >
        Solar Intelligence
      </Link>

      <div className="flex items-center gap-1">
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
          aria-label="Open menu"
          aria-expanded={menuOpen}
        >
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      {menuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-900/20"
            aria-hidden
            onClick={() => setMenuOpen(false)}
          />
          <nav
            ref={menuRef}
            className="fixed right-4 top-16 z-50 w-max min-w-40 rounded-xl border border-slate-200 bg-white py-2 shadow-lg sm:right-6"
            aria-label="Site navigation"
          >
            <Link
              href="/homes"
              onClick={() => setMenuOpen(false)}
              className={`block px-4 py-3 text-sm font-medium ${pathname === "/" || pathname.startsWith("/homes") ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} rounded-t-xl`}
            >
              Explorer
            </Link>
            <Link
              href="/about"
              onClick={() => setMenuOpen(false)}
              className={`block px-4 py-3 text-sm font-medium ${pathname === "/about" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} rounded-b-xl`}
            >
              About
            </Link>
            {/*
              Auth-gated menu items (Following, Permit Alerts, Sign in, Log out)
              are disabled while the site is public. Restore the block below
              when login is re-enabled.

              {user ? (
                <>
                  <Link href="/following" ...>Following</Link>
                  <Link href="/alerts" ...>Permit Alerts</Link>
                  <button onClick={handleLogout}>Log out</button>
                </>
              ) : (
                <Link href="/login">Sign in</Link>
              )}
            */}
          </nav>
        </>
      )}
    </header>
  );
}
