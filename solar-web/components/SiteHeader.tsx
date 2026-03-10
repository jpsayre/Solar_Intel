"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabaseBrowser } from "@/lib/supabase/client";

export default function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ id: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const menuRef = useRef<HTMLElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setMounted(true);
    supabaseBrowser.auth.getUser().then(({ data }) => setUser(data.user ?? null));
    const { data: { subscription } } = supabaseBrowser.auth.onAuthStateChange(() => {
      supabaseBrowser.auth.getUser().then(({ data }) => setUser(data.user ?? null));
    });
    return () => subscription.unsubscribe();
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

  async function handleLogout() {
    setMenuOpen(false);
    await supabaseBrowser.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  if (!mounted) return null;

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-slate-200/80 bg-white/95 px-4 py-3 backdrop-blur sm:px-6">
      <Link
        href="/about"
        className="text-lg font-bold tracking-tight text-slate-900 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 rounded"
      >
        Solar Intelligence
      </Link>

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
              href="/about"
              onClick={() => setMenuOpen(false)}
              className={`block px-4 py-3 text-sm font-medium ${pathname === "/about" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} rounded-t-xl`}
            >
              About
            </Link>
            <Link
              href="/pricing"
              onClick={() => setMenuOpen(false)}
              className={`block px-4 py-3 text-sm font-medium ${pathname === "/pricing" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"}`}
            >
              Pricing
            </Link>
            {user ? (
              <>
                <Link
                  href="/homes"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-4 py-3 text-sm font-medium ${pathname === "/" || pathname.startsWith("/homes") ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  Explorer
                </Link>
                <Link
                  href="/following"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-4 py-3 text-sm font-medium ${pathname === "/following" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  Following
                </Link>
                <Link
                  href="/alerts"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-4 py-3 text-sm font-medium ${pathname === "/alerts" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  Permit Alerts
                </Link>
                <div className="border-t border-slate-100 mt-1 pt-1">
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="block w-full px-4 py-3 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 rounded-b-xl"
                  >
                    Log out
                  </button>
                </div>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-4 py-3 text-sm font-medium ${pathname === "/login" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-4 py-3 text-sm font-medium ${pathname === "/signup" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} rounded-b-xl`}
                >
                  Sign up
                </Link>
              </>
            )}
          </nav>
        </>
      )}
    </header>
  );
}
