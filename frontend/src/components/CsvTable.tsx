import { useEffect, useMemo, useState } from "react";
import { fetchCsv } from "../lib/api";
import { Spinner } from "./ui";

export function useCsv(url: string | null) {
  const [data, setData] = useState<{ columns: string[]; rows: Record<string, string>[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    setData(null); setErr(null);
    fetchCsv(url).then(setData).catch((e) => setErr(String(e)));
  }, [url]);
  return { data, err };
}

/** Sortable, paginated table. `highlight(row)` marks rows in amber. */
export function CsvTable({ url, columns, highlight, pageSize = 10, caption }: {
  url: string; columns?: string[]; highlight?: (r: Record<string, string>) => boolean; pageSize?: number; caption?: string;
}) {
  const { data, err } = useCsv(url);
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(0);
  const rows = useMemo(() => {
    if (!data) return [];
    const r = [...data.rows];
    if (sort) {
      r.sort((a, b) => {
        const x = a[sort.col], y = b[sort.col];
        const nx = parseFloat(x), ny = parseFloat(y);
        const c = !isNaN(nx) && !isNaN(ny) ? nx - ny : String(x).localeCompare(String(y));
        return c * sort.dir;
      });
    }
    return r;
  }, [data, sort]);
  if (err) return <div className="text-xs text-red-300">Could not load {url}: {err}</div>;
  if (!data) return <div className="text-xs text-slate-500"><Spinner /> loading…</div>;
  const cols = columns?.filter((c) => data.columns.includes(c)) ?? data.columns;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const view = rows.slice(page * pageSize, (page + 1) * pageSize);
  return (
    <div className="space-y-1">
      {caption && <div className="text-[11px] text-slate-400">{caption}</div>}
      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full text-[11px]">
          <thead className="bg-slate-800/60 text-slate-300">
            <tr>
              {cols.map((c) => (
                <th key={c} className="cursor-pointer whitespace-nowrap px-2 py-1 text-left font-medium hover:text-white"
                  onClick={() => setSort((s) => ({ col: c, dir: s?.col === c && s.dir === 1 ? -1 : 1 }))}>
                  {c}{sort?.col === c ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono text-slate-300">
            {view.map((r, i) => (
              <tr key={i} className={`border-t border-slate-800 ${highlight?.(r) ? "bg-amber-500/15 text-amber-100" : ""}`}>
                {cols.map((c) => <td key={c} className="whitespace-nowrap px-2 py-0.5">{r[c]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="rounded px-1.5 hover:bg-slate-800 disabled:opacity-30">‹ prev</button>
          page {page + 1} / {pages} · {rows.length.toLocaleString()} rows
          <button disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} className="rounded px-1.5 hover:bg-slate-800 disabled:opacity-30">next ›</button>
        </div>
      )}
    </div>
  );
}
