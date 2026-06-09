"use client";

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const GridIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="6" height="6" rx="1.5" />
    <rect x="9" y="1" width="6" height="6" rx="1.5" />
    <rect x="1" y="9" width="6" height="6" rx="1.5" />
    <rect x="9" y="9" width="6" height="6" rx="1.5" />
  </svg>
);

const BarChartIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="9" width="3.5" height="6" rx="1" />
    <rect x="6.25" y="5" width="3.5" height="10" rx="1" />
    <rect x="11.5" y="1" width="3.5" height="14" rx="1" />
  </svg>
);

const HeatmapIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="4" height="4" rx="0.75" opacity="0.3" />
    <rect x="6" y="1" width="4" height="4" rx="0.75" opacity="0.6" />
    <rect x="11" y="1" width="4" height="4" rx="0.75" opacity="1" />
    <rect x="1" y="6" width="4" height="4" rx="0.75" opacity="0.5" />
    <rect x="6" y="6" width="4" height="4" rx="0.75" opacity="0.9" />
    <rect x="11" y="6" width="4" height="4" rx="0.75" opacity="0.7" />
    <rect x="1" y="11" width="4" height="4" rx="0.75" opacity="0.8" />
    <rect x="6" y="11" width="4" height="4" rx="0.75" opacity="0.4" />
    <rect x="11" y="11" width="4" height="4" rx="0.75" opacity="0.6" />
  </svg>
);

const AlertIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <path fillRule="evenodd" d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575L6.457 1.047zM9 11a1 1 0 11-2 0 1 1 0 012 0zm-.25-5.25a.75.75 0 00-1.5 0v2.5a.75.75 0 001.5 0v-2.5z" clipRule="evenodd" />
  </svg>
);

const StoreIcon = () => (
  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
    <path d="M2 3a1 1 0 00-1 1v1a2 2 0 001.987 2c.193 0 .38-.03.556-.082A2 2 0 005.5 8a2 2 0 001.957-1.082A2 2 0 009.5 8a2 2 0 001.957-1.082A2 2 0 0013.013 7 2 2 0 0015 5V4a1 1 0 00-1-1H2zm0 8v-1.73c.14.02.284.03.432.03a3.49 3.49 0 001.95-.594 3.49 3.49 0 002.118.594 3.49 3.49 0 002.118-.594 3.49 3.49 0 001.95.594c.147 0 .291-.01.432-.03V11a1 1 0 01-1 1H5a1 1 0 01-1-1v-2H3v2a1 1 0 01-1 1H2v-1z" />
  </svg>
);

const navItems: NavItem[] = [
  { id: "overview", label: "Overview",  icon: <GridIcon /> },
  { id: "metrics",  label: "Metrics",   icon: <BarChartIcon /> },
  { id: "heatmap",  label: "Heatmap",   icon: <HeatmapIcon /> },
  { id: "anomalies",label: "Anomalies", icon: <AlertIcon /> },
  { id: "stores",   label: "Stores",    icon: <StoreIcon /> },
];

interface Props {
  active: string;
  onNav: (id: string) => void;
  storeId: string;
}

export function Sidebar({ active, onNav, storeId }: Props) {
  return (
    <aside className="w-60 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col h-full">
      {/* Logo */}
      <div className="h-14 flex items-center px-5 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2a5 5 0 110 10A5 5 0 018 3zm0 2a3 3 0 100 6 3 3 0 000-6z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900 leading-tight">Store Intel</p>
            <p className="text-[10px] text-slate-400 leading-tight">Analytics Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              className={[
                "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-700",
              ].join(" ")}
            >
              <span className={isActive ? "text-brand-600" : "text-slate-400"}>
                {item.icon}
              </span>
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-3.5 h-3.5 text-slate-500" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 8a3 3 0 100-6 3 3 0 000 6zm-5 6s-1 0-1-1 1-4 6-4 6 3 6 4-1 1-1 1H3z"/>
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-slate-700 truncate">{storeId || "—"}</p>
            <p className="text-[10px] text-slate-400">Active store</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
