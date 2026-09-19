import { ReactNode } from "react";
import { RunMode } from "../lib/mode";

/** Solid rectangular status tags (government-service style); never colour alone — the text carries the meaning. */
const STATUS: Record<string, string> = {
  EXCEEDS: "bg-alert-red text-white", IMPLAUSIBLE: "bg-alert-red text-white",
  NO_MATCHING_REPORT_FOUND: "bg-alert-amber text-ink", INCONCLUSIVE: "bg-alert-amber text-ink",
  NOT_ASSESSED: "bg-[#dfe1e2] text-ink", BELOW: "bg-[#008817] text-white", BELOW_RQ: "bg-[#008817] text-white",
  CONSISTENT: "bg-[#008817] text-white", REPORTED: "bg-primary text-white",
};
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-sm px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide ${STATUS[status] ?? STATUS.NOT_ASSESSED}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

type Tone = "slate" | "amber" | "red" | "sky" | "emerald" | "violet";
const TONES: Record<Tone, string> = {
  slate: "border-rule text-muted", amber: "border-[#c2850c] text-[#936f38]", red: "border-alert-red text-alert-red",
  sky: "border-primary text-primary", emerald: "border-[#008817] text-[#008817]", violet: "border-[#54278f] text-[#54278f]",
};
export function Chip({ children, tone = "slate", title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return <span title={title} className={`inline-flex items-center gap-1 rounded-sm border bg-white px-1.5 py-px text-[11px] font-semibold ${TONES[tone]}`}>{children}</span>;
}

export function Card({ title, children, right, className = "", pad = true }: {
  title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-rule bg-paper px-5 py-3">
          <h3 className="text-base font-bold text-ink">{title}</h3>{right}
        </header>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex border border-primary" role="tablist">
      {options.map((o, i) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} disabled={o.disabled} title={o.title} onClick={() => onChange(o.value)}
          className={`font-bold transition-colors ${size === "sm" ? "px-3 py-1 text-xs" : "px-4 py-1.5 text-sm"} ${i ? "border-l border-primary" : ""} ${value === o.value ? "bg-primary text-white" : "bg-white text-primary hover:bg-[#e7f2f8]"} disabled:cursor-not-allowed disabled:border-rule disabled:text-[#a9aeb1]`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ModeToggle({ mode, setMode, liveAvailable }: { mode: RunMode; setMode: (m: RunMode) => void; liveAvailable?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="label">Mode</span>
      <Segmented size="sm" value={mode} onChange={setMode} options={[
        { value: "demo", label: "Demo" },
        { value: "live", label: "Live", disabled: !liveAvailable,
          title: liveAvailable ? "Live GPT agent with Huawei OMNI" : "Add API keys to .env in the project root and restart the backend" },
      ]} />
    </div>
  );
}

/** Brand mark: a small spinning globe (CSS only — the texture scrolls behind a shaded circular mask). */
export function Logo({ size = 32, speed = 18 }: { size?: number; speed?: number }) {
  return (
    <span aria-hidden className="globe-mark inline-block shrink-0 select-none rounded-full"
      style={{ width: size, height: size, ["--globe-w" as string]: `${size * 2}px`, animationDuration: `${speed}s` }} />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-paper ${className}`} />;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule border-t-primary ${className}`} aria-label="loading" />;
}

export function ShortHash({ hash }: { hash?: string }) {
  if (!hash) return <span className="text-muted">—</span>;
  return (
    <button className="font-mono text-[11px] text-muted hover:text-ink" title={`${hash}\n(click to copy)`} onClick={() => navigator.clipboard?.writeText(hash)}>
      sha256 {hash.slice(0, 12)}…
    </button>
  );
}
