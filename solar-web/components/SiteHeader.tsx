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

      <div className="flex items-center gap-1">
        {user && (
          <Link
            href="/alerts"
            className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
              pathname === "/alerts" ? "bg-amber-50 text-amber-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            } focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2`}
            aria-label="Permit alerts"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <span className="absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-white" />
          </Link>
        )}
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
              href="/about"
              onClick={() => setMenuOpen(false)}
              className={`block px-4 py-3 text-sm font-medium ${pathname === "/about" ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} rounded-t-xl`}
            >
              About
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
