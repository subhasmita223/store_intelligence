"use client";

import { useEffect, useState } from "react";
import { getMetrics } from "@/lib/api";

interface Metrics {
  store_id: string;
  date: string;
  unique_visitors: number;
  conversion_rate: number;
  avg_dwell_per_zone: Record<string, number>;
  current_queue_depth: number;
  abandonment_rate: number;
}

interface Props {
  storeId: string;
  forDate: string;
}

/* ── icons ──────────────────────────────────────────────────── */
const VisitorsIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
    <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z" />
  </svg>
);
const ConversionIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L11 10.586 14.586 7H12z" clipRule="evenodd" />
  </svg>
);
const QueueIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
  </svg>
);
const AbandonIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M12 13a1 1 0 100 2h5a1 1 0 001-1V9a1 1 0 10-2 0v2.586l-4.293-4.293a1 1 0 00-1.414 0L8 9.586 3.707 5.293a1 1 0 00-1.414 1.414l5 5a1 1 0 001.414 0L11 9.414 14.586 13H12z" clipRule="evenodd" />
  </svg>
);

const kpiConfig = [
  {
    key:   "unique_visitors",
    label: "Unique Visitors",
    icon:  <VisitorsIcon />,
    iconBg: "bg-violet-100 text-violet-600",
    format: (v: number) => v.toLocaleString(),
    unit:  "visitors today",
    highlight: false,
  },
  {
    key:   "conversion_rate",
    label: "Conversion Rate",
    icon:  <ConversionIcon />,
    iconBg: "bg-emerald-100 text-emerald-600",
    format: (v: number) => `${(v * 100).toFixed(1)}%`,
    unit:  "completed purchase",
    highlight: true,
  },
  {
    key:   "current_queue_depth",
    label: "Queue Depth",
    icon:  <QueueIcon />,
    iconBg: "bg-amber-100 text-amber-600",
    format: (v: number) => v.toLocaleString(),
    unit:  "people in queue now",
    highlight: false,
  },
  {
    key:   "abandonment_rate",
    label: "Abandonment Rate",
    icon:  <AbandonIcon />,
    iconBg: "bg-red-100 text-red-500",
    format: (v: number) => `${(v * 100).toFixed(1)}%`,
    unit:  "left without purchase",
    highlight: false,
  },
] as const;

export function MetricsPanel({ storeId, forDate }: Props) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [stale,   setStale]   = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getMetrics(storeId, forDate);
        if (!cancelled) { setMetrics(data as Metrics); setStale(false); }
      } catch { if (!cancelled) setStale(true); }
    };
    load();
    const id = setInterval(load, 5_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [storeId, forDate]);

  return (
    <>
      {/* ── KPI cards ─────────────────────────────────────────── */}
      <div id="overview">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Key Metrics</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {forDate} · {stale
                ? <span className="text-amber-500">Feed stale</span>
                : <span className="text-emerald-500">Live</span>}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
          {kpiConfig.map((cfg) => {
            const value = metrics ? (metrics as unknown as Record<string, number>)[cfg.key] : null;
            return (
              <div
                key={cfg.key}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-card hover:shadow-card-hover transition-shadow"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${cfg.iconBg}`}>
                    {cfg.icon}
                  </div>
                  <span className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">
                    {cfg.label}
                  </span>
                </div>
                <div className="mt-1">
                  <p className="text-3xl font-bold tabular-nums text-slate-900 leading-none">
                    {value === null ? (
                      <span className="text-slate-300">—</span>
                    ) : (
                      cfg.format(value)
                    )}
                  </p>
                  <p className="text-xs text-slate-400 mt-1.5">{cfg.unit}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Zone Analytics ────────────────────────────────────── */}
      <div id="metrics">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-900">Zone Analytics</h2>
          <p className="text-xs text-slate-400 mt-0.5">Average dwell time by zone · ranked by engagement</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-card overflow-hidden mb-8">
          {/* header row */}
          <div className="grid grid-cols-12 px-5 py-3 border-b border-slate-100 bg-slate-50">
            <span className="col-span-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">#</span>
            <span className="col-span-4 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Zone</span>
            <span className="col-span-4 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Utilization</span>
            <span className="col-span-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-right">Dwell</span>
          </div>

          {metrics && Object.keys(metrics.avg_dwell_per_zone).length > 0 ? (() => {
            const entries = Object.entries(metrics.avg_dwell_per_zone)
              .sort((a, b) => b[1] - a[1]);
            const max = entries[0]?.[1] ?? 1;

            return entries.map(([zone, ms], i) => {
              const pct = Math.round((ms / max) * 100);
              const secs = ms / 1000;
              const label = secs >= 60
                ? `${(secs / 60).toFixed(1)}m`
                : `${secs.toFixed(1)}s`;

              return (
                <div
                  key={zone}
                  className="grid grid-cols-12 px-5 py-3.5 items-center border-b border-slate-50 last:border-0 hover:bg-slate-50/60 transition-colors"
                >
                  <span className="col-span-1 text-sm font-semibold tabular-nums text-slate-300">
                    {i + 1}
                  </span>
                  <div className="col-span-4">
                    <p className="text-sm font-medium text-slate-800 truncate">{zone}</p>
                  </div>
                  <div className="col-span-4 flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-600 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-slate-400 tabular-nums w-7 text-right">{pct}%</span>
                  </div>
                  <div className="col-span-2 text-right">
                    <span className="text-sm font-semibold tabular-nums text-slate-700">{label}</span>
                  </div>
                </div>
              );
            });
          })() : (
            <div className="px-5 py-10 text-center text-sm text-slate-400">
              {metrics ? "No zone data for this date." : "Loading…"}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
