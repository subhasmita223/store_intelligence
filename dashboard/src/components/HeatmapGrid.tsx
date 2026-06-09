"use client";

import { useEffect, useState } from "react";
import { getHeatmap } from "@/lib/api";

interface ZoneScore {
  zone_id: string;
  zone_name: string;
  score: number;
  visit_count: number;
  avg_dwell_ms: number;
}

interface Props {
  storeId: string;
  forDate: string;
}

function scoreToColor(score: number): string {
  // cool violet → warm amber → hot red
  if (score >= 80) return "bg-red-500";
  if (score >= 60) return "bg-orange-400";
  if (score >= 40) return "bg-amber-400";
  if (score >= 20) return "bg-emerald-400";
  return "bg-sky-300";
}

function scoreToBadge(score: number): { text: string; cls: string } {
  if (score >= 80) return { text: "Hot",    cls: "bg-red-100 text-red-700" };
  if (score >= 60) return { text: "High",   cls: "bg-orange-100 text-orange-700" };
  if (score >= 40) return { text: "Medium", cls: "bg-amber-100 text-amber-700" };
  if (score >= 20) return { text: "Low",    cls: "bg-emerald-100 text-emerald-700" };
  return               { text: "Cold",    cls: "bg-sky-100 text-sky-700" };
}

function formatDwell(ms: number): string {
  const s = ms / 1000;
  if (s >= 60) return `${(s / 60).toFixed(1)}m`;
  return `${s.toFixed(1)}s`;
}

export function HeatmapGrid({ storeId, forDate }: Props) {
  const [zones,         setZones]         = useState<ZoneScore[]>([]);
  const [lowConfidence, setLowConfidence] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getHeatmap(storeId, forDate);
        if (cancelled) return;
        const d = data as { zones: ZoneScore[]; data_confidence: boolean };
        setZones(d.zones ?? []);
        setLowConfidence(!d.data_confidence);
      } catch {/* silent */}
    };
    load();
    const id = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [storeId, forDate]);

  const sorted = [...zones].sort((a, b) => b.score - a.score);

  return (
    <div id="heatmap" className="mb-8">
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Zone Heatmap</h2>
          <p className="text-xs text-slate-400 mt-0.5">Engagement score by zone · 0 = cold · 100 = peak</p>
        </div>

        {lowConfidence && (
          <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
              <path d="M6 1a5 5 0 100 10A5 5 0 006 1zm.5 7.5h-1v-1h1v1zm0-2.5h-1V3h1v3z"/>
            </svg>
            Low confidence · &lt;20 sessions
          </span>
        )}
      </div>

      {zones.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center shadow-card">
          <p className="text-sm text-slate-400">No zone data for {forDate}.</p>
        </div>
      ) : (
        <>
          {/* Score legend */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-card p-5 mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Score Scale</span>
              <div className="flex items-center gap-3 text-[10px] text-slate-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-sky-300 inline-block"/> Cold (0–19)</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-400 inline-block"/> Low (20–39)</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-amber-400 inline-block"/> Medium (40–59)</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-400 inline-block"/> High (60–79)</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-red-500 inline-block"/> Hot (80–100)</span>
              </div>
            </div>
            {/* Gradient bar */}
            <div
              className="h-2 rounded-full"
              style={{
                background:
                  "linear-gradient(to right, #7dd3fc, #34d399, #fbbf24, #fb923c, #ef4444)",
              }}
            />
            <div className="flex justify-between mt-1 text-[9px] text-slate-400 tabular-nums">
              <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
            </div>
          </div>

          {/* Zone cards grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {sorted.map((zone, i) => {
              const badge = scoreToBadge(zone.score);
              return (
                <div
                  key={zone.zone_id}
                  className="bg-white rounded-xl border border-slate-200 shadow-card hover:shadow-card-hover transition-shadow p-5 flex flex-col gap-3"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-semibold tabular-nums text-slate-300 w-4 flex-shrink-0">
                        {i + 1}
                      </span>
                      <p className="text-sm font-semibold text-slate-800 truncate">{zone.zone_name}</p>
                    </div>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${badge.cls}`}>
                      {badge.text}
                    </span>
                  </div>

                  {/* Score bar */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Engagement</span>
                      <span className="text-sm font-bold tabular-nums text-slate-800">{zone.score}</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${scoreToColor(zone.score)}`}
                        style={{ width: `${zone.score}%` }}
                      />
                    </div>
                  </div>

                  {/* Stats row */}
                  <div className="grid grid-cols-2 gap-3 pt-1 border-t border-slate-50">
                    <div>
                      <p className="text-[10px] text-slate-400 mb-0.5">Visits</p>
                      <p className="text-sm font-semibold tabular-nums text-slate-700">
                        {zone.visit_count.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 mb-0.5">Avg Dwell</p>
                      <p className="text-sm font-semibold tabular-nums text-slate-700">
                        {formatDwell(zone.avg_dwell_ms)}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
