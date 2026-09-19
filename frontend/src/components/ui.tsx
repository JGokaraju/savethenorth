import { ReactNode } from "react";

const STATUS_STYLES: Record<string, string> = {
  EXCEEDS: "bg-red-500/15 text-red-300 ring-red-500/40",
  IMPLAUSIBLE: "bg-red-500/15 text-red-300 ring-red-500/40",
  NO_MATCHING_REPORT_FOUND: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  INCONCLUSIVE: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  NOT_ASSESSED: "bg-slate-500/15 text-slate-300 ring-slate-500/40",
  BELOW: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  BELOW_RQ: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  CONSISTENT: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  REPORTED: "bg-sky-500/15 text-sky-300 ring-sky-500/40",
};
const STATUS_ICON: Record<string, string> = {
  EXCEEDS: "▲", IMPLAUSIBLE: "!", NO_MATCHING_REPORT_FOUND: "?", INCONCLUSIVE: "~", NOT_ASSESSED: "–",
  BELOW: "▼", BELOW_RQ: "▼", CONSISTENT: "✓", REPORTED: "✓",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-semibold ring-1 ${STATUS_STYLES[status] ?? STATUS_STYLES.NOT_ASSESSED}`}>
      <span aria-hidden>{STATUS_ICON[status] ?? "•"}</span>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function Chip({ children, tone = "slate", title }: { children: ReactNode; tone?: "slate" | "amber" | "red" | "sky" | "emerald" | "violet"; title?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-800 text-slate-300 ring-slate-700",
    amber: "bg-amber-500/10 text-amber-300 ring-amber-500/40",
    red: "bg-red-500/10 text-red-300 ring-red-500/40",
    sky: "bg-sky-500/10 text-sky-300 ring-sky-500/40",
    emerald: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/40",
    violet: "bg-violet-500/10 text-violet-300 ring-violet-500/40",
  };
  return <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ring-1 ${tones[tone]}`}>{children}</span>;
}

export function ModeBadge({ mode }: { mode: string | null | undefined }) {
  const m = (mode ?? "MOCK").toUpperCase();
  const tone = m === "LIVE" ? "emerald" : m === "REPLAY" ? "sky" : "amber";
  return <Chip tone={tone as any} title={m === "MOCK" ? "No API keys: scripted agent + mock OMNI" : undefined}>● {m}</Chip>;
}

export function Card({ title, children, right, className = "" }: { title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-800 bg-slate-900/60 ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
          <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-800/80 ${className}`} />;
}

export function Spinner() {
  return <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" aria-label="loading" />;
}

export function ShortHash({ hash }: { hash?: string }) {
  if (!hash) return <span className="text-slate-500">—</span>;
  return (
    <button
      className="font-mono text-[11px] text-slate-400 hover:text-slate-200"
      title={`${hash}\n(click to copy)`}
      onClick={() => navigator.clipboard?.writeText(hash)}
    >
      sha256 {hash.slice(0, 12)}…
    </button>
  );
}
