import { ReactNode } from "react";
import { RunMode } from "../lib/mode";

/** Status tags: tinted, uppercase, never colour alone (the text carries the meaning). */
const STATUS: Record<string, string> = {
  EXCEEDS: "border-alert-red/60 bg-alert-red/15 text-alert-red", IMPLAUSIBLE: "border-alert-red/60 bg-alert-red/15 text-alert-red",
  NO_MATCHING_REPORT_FOUND: "border-alert-amber/60 bg-alert-amber/15 text-alert-amber",
  INCONCLUSIVE: "border-alert-amber/60 bg-alert-amber/15 text-alert-amber",
  NOT_ASSESSED: "border-rule bg-panel2 text-muted",
  BELOW: "border-alert-green/60 bg-alert-green/15 text-alert-green", BELOW_RQ: "border-alert-green/60 bg-alert-green/15 text-alert-green",
  CONSISTENT: "border-alert-green/60 bg-alert-green/15 text-alert-green", REPORTED: "border-primary/60 bg-primary/15 text-primary",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block whitespace-nowrap border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${STATUS[status] ?? STATUS.NOT_ASSESSED}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

type Tone = "slate" | "amber" | "red" | "sky" | "emerald" | "violet";
const TONES: Record<Tone, string> = {
  slate: "border-rule text-muted", amber: "border-alert-amber/50 text-alert-amber", red: "border-alert-red/50 text-alert-red",
  sky: "border-primary/50 text-primary", emerald: "border-alert-green/50 text-alert-green", violet: "border-accent/50 text-accent",
};

export function Chip({ children, tone = "slate", title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return <span title={title} className={`inline-flex items-center gap-1 border bg-transparent px-1.5 py-px text-[11px] ${TONES[tone]}`}>{children}</span>;
}

/** Gold small-caps label with a rule, as in the template. */
export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`eyebrow ${className}`}>{children}</p>;
}

export function Card({ title, children, right, className = "", pad = true }: {
  title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-rule px-5 py-3">
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
    <div className="inline-flex border border-rule" role="tablist">
      {options.map((o, i) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} disabled={o.disabled} title={o.title} onClick={() => onChange(o.value)}
          className={`font-semibold uppercase tracking-[0.12em] transition-colors ${size === "sm" ? "px-3 py-1.5 text-[11px]" : "px-4 py-2 text-xs"} ${i ? "border-l border-rule" : ""} ${
            value === o.value ? "bg-accent text-page" : "text-muted hover:text-ink"} disabled:cursor-not-allowed disabled:text-muted/40`}>
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

export function Logo({ size = 32, speed = 18, spin = true }: { size?: number; speed?: number; spin?: boolean }) {
  return (
    <span aria-hidden className={`globe-mark inline-block shrink-0 select-none rounded-full ${spin ? "" : "globe-still"}`}
      style={{ width: size, height: size, ["--globe-w" as string]: `${size * 2}px`, animationDuration: `${speed}s` }} />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-panel2 ${className}`} />;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule border-t-accent ${className}`} aria-label="loading" />;
}

export function ShortHash({ hash }: { hash?: string }) {
  if (!hash) return <span className="text-muted">—</span>;
  return (
    <button className="font-mono text-[11px] text-muted hover:text-ink" title={`${hash}\n(click to copy)`} onClick={() => navigator.clipboard?.writeText(hash)}>
      sha256 {hash.slice(0, 12)}…
    </button>
  );
}
