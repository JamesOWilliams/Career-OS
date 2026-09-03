export function PageHeader({ eyebrow, title, subtitle, children }) {
  return (
    <div className="border-b border-[#243044] bg-[#0E1420]/80 backdrop-blur-md px-8 py-6 sticky top-0 z-30 flex items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <div className="font-mono text-[11px] tracking-widest uppercase text-cyan-400 mb-1">
            {eyebrow}
          </div>
        )}
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-slate-400 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}

const TRACK_STYLES = {
  civilian: "text-sky-300 border-sky-500/40 bg-sky-500/10",
  military: "text-lime-300 border-lime-500/40 bg-lime-500/10",
  intellectual_property: "text-purple-300 border-purple-500/40 bg-purple-500/10",
};

export function TrackBadge({ track }) {
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${
        TRACK_STYLES[track] || TRACK_STYLES.civilian
      }`}
    >
      {(track || "").replace("_", " ")}
    </span>
  );
}

export function StateBadge({ state }) {
  const styles =
    state === "VERIFIED"
      ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
      : "text-amber-400 border-amber-500/40 bg-amber-500/10";
  return (
    <span className={`font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${styles}`}>
      {state}
    </span>
  );
}

export function StrengthBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 65 ? "#34D399" : pct >= 40 ? "#22D3EE" : "#FBBF24";
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full bg-[#0B0F17] overflow-hidden border border-[#243044]">
        <div className="strength-bar h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs text-slate-300 w-9 text-right">{pct}%</span>
    </div>
  );
}

const WEIGHT_STYLES = {
  primary: "text-cyan-300 border-cyan-500/50 bg-cyan-500/15",
  supporting: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
  contextual: "text-slate-300 border-slate-500/40 bg-slate-500/10",
  chronology: "text-slate-400 border-slate-600/40 bg-slate-600/10",
};

export function WeightBadge({ weight }) {
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${
        WEIGHT_STYLES[weight] || WEIGHT_STYLES.contextual
      }`}
    >
      {weight}
    </span>
  );
}

export function TierPill({ tier }) {
  const map = {
    1: "text-rose-300 border-rose-500/40 bg-rose-500/10",
    2: "text-amber-300 border-amber-500/40 bg-amber-500/10",
    3: "text-sky-300 border-sky-500/40 bg-sky-500/10",
    4: "text-slate-400 border-slate-600/40 bg-slate-600/10",
  };
  return (
    <span className={`font-mono text-[10px] px-2 py-0.5 rounded border ${map[tier] || map[3]}`}>
      TIER {tier}
    </span>
  );
}
