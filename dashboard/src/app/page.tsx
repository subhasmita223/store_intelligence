"use client";

import { useEffect, useRef, useState } from "react";
import { getHealth } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { MetricsPanel } from "@/components/MetricsPanel";
import { HeatmapGrid } from "@/components/HeatmapGrid";
import { AnomalyFeed } from "@/components/AnomalyFeed";

/* ── tiny helpers ────────────────────────────────────────────── */
function ChevronIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" viewBox="0 0 12 12" fill="currentColor">
      <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
    </svg>
  );
}
function CalendarIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <path d="M5 0a1 1 0 011 1v1h4V1a1 1 0 112 0v1h1a2 2 0 012 2v9a2 2 0 01-2 2H3a2 2 0 01-2-2V4a2 2 0 012-2h1V1a1 1 0 011-1zm8 5H3v7h10V5z"/>
    </svg>
  );
}

const SECTIONS = ["overview", "metrics", "heatmap", "anomalies"] as const;

export default function DashboardPage() {
  const [stores,        setStores]        = useState<string[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [forDate,       setForDate]       = useState("2026-03-08");
  const [activeSection, setActiveSection] = useState("overview");
  const [lastUpdated,   setLastUpdated]   = useState<Date | null>(null);
  const mainRef = useRef<HTMLElement>(null);

  /* ── load stores from /health ──────────────────────────────── */
  useEffect(() => {
    getHealth()
      .then((h: unknown) => {
        const ids = Object.keys(
          (h as { stores: Record<string, unknown> }).stores ?? {}
        );
        setStores(ids);
        if (ids.length) setSelectedStore(ids[0]);
        setLastUpdated(new Date());
      })
      .catch(() => {
        setStores(["ST1076"]);
        setSelectedStore("ST1076");
      });
  }, []);

  /* ── update "last updated" clock periodically ──────────────── */
  useEffect(() => {
    const id = setInterval(() => setLastUpdated(new Date()), 5_000);
    return () => clearInterval(id);
  }, []);

  /* ── scroll to section on sidebar nav ─────────────────────── */
  function scrollToSection(id: string) {
    setActiveSection(id);
    document
      .getElementById(id === "overview" ? "overview" : id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ── track active section on scroll ───────────────────────── */
  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const handler = () => {
      for (const sec of [...SECTIONS].reverse()) {
        const node = document.getElementById(sec);
        if (node && el.scrollTop + 100 >= node.offsetTop) {
          setActiveSection(sec);
          break;
        }
      }
    };
    el.addEventListener("scroll", handler, { passive: true });
    return () => el.removeEventListener("scroll", handler);
  }, []);

  /* ── relative time ─────────────────────────────────────────── */
  function relativeTime(d: Date | null): string {
    if (!d) return "—";
    const secs = Math.round((Date.now() - d.getTime()) / 1000);
    if (secs < 5)  return "just now";
    if (secs < 60) return `${secs}s ago`;
    return `${Math.round(secs / 60)}m ago`;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <Sidebar
        active={activeSection}
        onNav={scrollToSection}
        storeId={selectedStore}
      />

      {/* ── Main column ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* ── Top header ──────────────────────────────────────── */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 gap-4 flex-shrink-0">
          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mr-2">
            <span className="font-medium text-slate-600">Store Intelligence</span>
            <ChevronIcon />
            <span className="capitalize">{activeSection}</span>
          </div>

          <div className="flex-1" />

          {/* Store selector */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-white hover:border-slate-300 transition-colors cursor-pointer">
            <div className="w-4 h-4 rounded-sm bg-brand-600 flex-shrink-0" />
            <select
              value={selectedStore}
              onChange={(e) => setSelectedStore(e.target.value)}
              className="text-xs font-medium text-slate-700 bg-transparent outline-none cursor-pointer pr-1"
            >
              {stores.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Date selector */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-white hover:border-slate-300 transition-colors">
            <CalendarIcon />
            <input
              type="date"
              value={forDate}
              onChange={(e) => setForDate(e.target.value)}
              className="text-xs font-medium text-slate-700 bg-transparent outline-none cursor-pointer"
            />
          </div>

          {/* Last updated */}
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400 pl-2 border-l border-slate-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Updated {relativeTime(lastUpdated)}
          </div>
        </header>

        {/* ── Scrollable content ──────────────────────────────── */}
        <main
          ref={mainRef}
          className="flex-1 overflow-y-auto scrollbar-none"
        >
          {selectedStore ? (
            <div className="max-w-5xl mx-auto px-6 py-6 space-y-0">
              {/* Page title */}
              <div className="mb-6">
                <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  {selectedStore} · {forDate}
                </p>
              </div>

              {/* Sections (IDs match sidebar nav) */}
              <MetricsPanel storeId={selectedStore} forDate={forDate} />
              <HeatmapGrid  storeId={selectedStore} forDate={forDate} />
              <AnomalyFeed  storeId={selectedStore} />

              {/* Bottom padding */}
              <div className="h-12" />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center h-full">
              <div className="text-center">
                <div className="w-12 h-12 rounded-xl bg-brand-100 flex items-center justify-center mx-auto mb-4">
                  <div className="w-5 h-5 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="text-sm font-medium text-slate-600">Connecting…</p>
                <p className="text-xs text-slate-400 mt-1">Loading store data</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
