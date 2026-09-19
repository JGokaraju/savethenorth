import { ReactNode } from "react";
import { RunMode } from "../lib/mode";

const STATUS: Record<string, { cls: string; icon: string }> = {
  EXCEEDS: { cls: "bg-red-50 text-red-700 ring-red-200", icon: "▲" },
  IMPLAUSIBLE: { cls: "bg-red-50 text-red-700 ring-red-200", icon: "!" },
  NO_MATCHING_REPORT_FOUND: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: "?" },
  INCONCLUSIVE: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: "~" },
  NOT_ASSESSED: { cls: "bg-slate-100 text-slate-500 ring-slate-200", icon: "–" },
  BELOW: { cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: "▼" },
  BELOW_RQ: { cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: "▼" },
  CONSISTENT: { cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: "✓" },
  REPORTED: { cls: "bg-sky-50 text-sky-700 ring-sky-200", icon: "✓" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.NOT_ASSESSED;
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${s.cls}`}>
      <span aria-hidden>{s.icon}</span>{status.replace(/_/g, " ")}
    </span>
  );
}

type Tone = "slate" | "amber" | "red" | "sky" | "emerald" | "violet";
const TONES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
};
export function Chip({ children, tone = "slate", title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ${TONES[tone]}`}>{children}</span>;
}

export function Card({ title, children, right, className = "", pad = true }: {
  title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`glass ${className}`}>
      {title && (
        <header className="flex items-center justify-between px-6 pt-5">
          <h3 className="text-[15px] font-semibold text-slate-800">{title}</h3>{right}
        </header>
      )}
      <div className={pad ? "p-6 pt-4" : ""}>{children}</div>
    </section>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-xl bg-slate-100/90 p-1" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} disabled={o.disabled} title={o.title}
          onClick={() => onChange(o.value)}
          className={`rounded-lg font-medium transition ${size === "sm" ? "px-2.5 py-1 text-[11px]" : "px-3.5 py-1.5 text-sm"} ${value === o.value ? "bg-[#2b2f33] text-white shadow" : "text-slate-500 hover:text-slate-800"} disabled:cursor-not-allowed disabled:opacity-40`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ModeToggle({ mode, setMode, liveAvailable }: { mode: RunMode; setMode: (m: RunMode) => void; liveAvailable?: boolean }) {
  return (
    <Segmented size="sm" value={mode} onChange={setMode} options={[
      { value: "demo", label: "Demo" },
      { value: "live", label: "Live", disabled: !liveAvailable,
        title: liveAvailable ? "Run the live GPT agent with Huawei OMNI" : "Add API keys to the .env file in the project root, then restart the backend" },
    ]} />
  );
}

export function Logo({ size = 32 }: { size?: number }) {
  return <img src="/logo.png" alt="" width={size} height={size} className="select-none" style={{ width: size, height: size }} />;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-slate-200/70 ${className}`} />;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700 ${className}`} aria-label="loading" />;
}

export function ShortHash({ hash }: { hash?: string }) {
  if (!hash) return <span className="text-slate-400">—</span>;
  return (
    <button className="font-mono text-[11px] text-slate-400 hover:text-slate-700" title={`${hash}\n(click to copy)`}
      onClick={() => navigator.clipboard?.writeText(hash)}>
      sha256 {hash.slice(0, 12)}…
    </button>
  );
}
