"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/purchase", label: "Purchase" },
  { href: "/faq", label: "FAQ" },
  { href: "/contact", label: "Contact" },
];

export default function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

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

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between border-b border-slate-200/80 bg-white/95 px-4 py-3 backdrop-blur sm:px-6">
      <Link
        href="/"
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
            {NAV_LINKS.map((link, i) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`block px-4 py-3 text-sm font-medium ${pathname === link.href ? "bg-amber-50 text-amber-800" : "text-slate-700 hover:bg-slate-50"} ${i === 0 ? "rounded-t-xl" : ""} ${i === NAV_LINKS.length - 1 ? "rounded-b-xl" : ""}`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </>
      )}
    </header>
  );
}
