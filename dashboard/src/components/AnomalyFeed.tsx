"use client";

import { useEffect, useState } from "react";
import { getAnomalies } from "@/lib/api";

interface Anomaly {
  type: string;
  severity: "INFO" | "WARN" | "CRITICAL";
  detail: string;
  suggested_action: string;
}

interface Props {
  storeId: string;
}

const severityConfig = {
  CRITICAL: {
    label:    "Critical",
    bar:      "bg-red-500",
    badge:    "bg-red-100 text-red-700 border-red-200",
    icon:     "text-red-500",
    cardRing: "border-l-red-500",
  },
  WARN: {
    label:    "Warning",
    bar:      "bg-amber-400",
    badge:    "bg-amber-50 text-amber-700 border-amber-200",
    icon:     "text-amber-500",
    cardRing: "border-l-amber-400",
  },
  INFO: {
    label:    "Info",
    bar:      "bg-blue-400",
    badge:    "bg-blue-50 text-blue-700 border-blue-200",
    icon:     "text-blue-500",
    cardRing: "border-l-blue-400",
  },
};

const CriticalIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <path fillRule="evenodd" d="M8 1a7 7 0 100 14A7 7 0 008 1zM7 5a1 1 0 112 0v3a1 1 0 11-2 0V5zm1 7a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
  </svg>
);
const WarnIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <path fillRule="evenodd" d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575L6.457 1.047zM9 11a1 1 0 11-2 0 1 1 0 012 0zm-.25-5.25a.75.75 0 00-1.5 0v2.5a.75.75 0 001.5 0v-2.5z" clipRule="evenodd" />
  </svg>
);
const InfoIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <path fillRule="evenodd" d="M8 1a7 7 0 100 14A7 7 0 008 1zM8 5a1 1 0 100 2 1 1 0 000-2zm-1 3a1 1 0 011-1h.5a.5.5 0 01.5.5v3.5h.5a.5.5 0 010 1h-2a.5.5 0 010-1h.5V8.5H8a1 1 0 01-1-1z" clipRule="evenodd" />
  </svg>
);

const icons: Record<string, React.ReactNode> = {
  CRITICAL: <CriticalIcon />,
  WARN:     <WarnIcon />,
  INFO:     <InfoIcon />,
};

function typeLabel(type: string): string {
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function AnomalyFeed({ storeId }: Props) {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getAnomalies(storeId);
        if (!cancelled) {
          setAnomalies((data as { anomalies: Anomaly[] }).anomalies ?? []);
          setLoading(false);
        }
      } catch { if (!cancelled) setLoading(false); }
    };
    load();
    const id = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [storeId]);

  const criticals = anomalies.filter((a) => a.severity === "CRITICAL");
  const warnings  = anomalies.filter((a) => a.severity === "WARN");
  const infos     = anomalies.filter((a) => a.severity === "INFO");
  const ordered   = [...criticals, ...warnings, ...infos];

  return (
    <div id="anomalies">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Anomaly Center</h2>
          <p className="text-xs text-slate-400 mt-0.5">Real-time operational alerts · refreshes every 30s</p>
        </div>

        {anomalies.length > 0 && (
          <div className="flex items-center gap-2">
            {criticals.length > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-red-100 text-red-700 border border-red-200">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                {criticals.length} Critical
              </span>
            )}
            {warnings.length > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                {warnings.length} Warning
              </span>
            )}
            {infos.length > 0 && (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                {infos.length} Info
              </span>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-card p-10 text-center">
          <p className="text-sm text-slate-400">Loading anomalies…</p>
        </div>
      ) : ordered.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-card p-8 text-center">
          <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-3">
            <svg className="w-5 h-5 text-emerald-600" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          </div>
          <p className="text-sm font-semibold text-slate-700">All clear</p>
          <p className="text-xs text-slate-400 mt-1">No active anomalies detected</p>
        </div>
      ) : (
        <div className="space-y-3">
          {ordered.map((a, i) => {
            const cfg = severityConfig[a.severity] ?? severityConfig.INFO;
            return (
              <div
                key={i}
                className={[
                  "bg-white rounded-xl border border-slate-200 shadow-card",
                  "border-l-4 pl-5 pr-5 py-4",
                  cfg.cardRing,
                  "hover:shadow-card-hover transition-shadow",
                ].join(" ")}
              >
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div className={`mt-0.5 flex-shrink-0 ${cfg.icon}`}>
                    {icons[a.severity]}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${cfg.badge}`}>
                        {cfg.label}
                      </span>
                      <span className="text-sm font-semibold text-slate-800">
                        {typeLabel(a.type)}
                      </span>
                    </div>

                    <p className="text-xs text-slate-500 leading-relaxed">{a.detail}</p>

                    <div className="flex items-start gap-1.5 mt-2">
                      <svg className="w-3 h-3 text-brand-500 mt-0.5 flex-shrink-0" viewBox="0 0 12 12" fill="currentColor">
                        <path d="M6 0a6 6 0 100 12A6 6 0 006 0zm.5 9h-1V5.5h1V9zm0-4.5h-1v-1h1v1z"/>
                      </svg>
                      <p className="text-[11px] text-brand-600 font-medium leading-relaxed">
                        {a.suggested_action}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
