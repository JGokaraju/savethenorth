import { useEffect, useMemo, useRef, useState } from "react";
import { api, Facility, fetchCsv, GeoResult, runFileUrl } from "../lib/api";
import { RunState } from "../lib/useRun";
import { Plot } from "./Plot";
import { Chip } from "./ui";

export function LocationSearch({ initial, onPick, placeholder = "Search a facility, city or county…", className = "" }: {
  initial?: string; onPick: (r: GeoResult) => void; placeholder?: string; className?: string;
}) {
  const [q, setQ] = useState(initial ?? "");
  const [res, setRes] = useState<GeoResult[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const timer = useRef<number>();
  useEffect(() => { if (initial !== undefined) setQ(initial); }, [initial]);
  const search = (v: string) => {
    setQ(v);
    window.clearTimeout(timer.current);
    if (!v.trim()) { setRes([]); return; }
    timer.current = window.setTimeout(async () => {
      try { setRes(await api.geocode(v)); setOpen(true); setActive(0); } catch { setRes([]); }
    }, 180);
  };
  const pick = (r: GeoResult) => { setQ(r.label); setOpen(false); onPick(r); };
  return (
    <div className={`relative ${className}`}>
      <input
        value={q}
        onChange={(e) => search(e.target.value)}
        onFocus={() => res.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, res.length - 1));
          if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          if (e.key === "Enter" && res[active]) pick(res[active]);
        }}
        placeholder={placeholder}
        aria-label="Location search"
        className="input"
      />
      {open && res.length > 0 && (
        <ul className="absolute z-40 mt-1 max-h-72 w-full min-w-[280px] overflow-auto border border-rule bg-panel2">
          {res.map((r, i) => (
            <li key={r.label + i}>
              <button onMouseDown={() => pick(r)}
                className={`flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-sm ${i === active ? "bg-panel text-accent" : "hover:bg-panel"}`}>
                <span>
                  <span className="text-ink">{r.label}</span>
                  {r.nearest_facility && r.kind !== "facility" && (
                    <span className="block text-[11px] text-muted">nearest facility: {r.nearest_facility.name} ({r.nearest_facility.distance_km} km)</span>
                  )}
                </span>
                <span className="text-[10px] uppercase tracking-[0.16em] text-muted">{r.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AvailabilityChips({ f }: { f: Facility }) {
  const a = f.availability ?? {};
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(a).map(([k, v]) => (
        <Chip key={k} tone={!v.available ? "slate" : v.quality === "synthetic" ? "violet" : v.quality === "low" ? "amber" : "emerald"}
          title={!v.available ? "not available" : v.quality === "synthetic" ? "SYNTHETIC placeholder" : v.quality === "low" ? "low quality" : "available"}>
          {v.available ? "✓" : "✗"} {k}{v.quality === "synthetic" ? " (synthetic)" : v.quality === "low" ? " (low-q)" : ""}
        </Chip>
      ))}
    </div>
  );
}

export function FacilityCard({ f }: { f: Facility }) {
  const rows: [string, any][] = [
    ["Operator", f.operator], ["Location", `${f.nearest_city ? f.nearest_city + ", " : ""}${f.county ?? ""} County, ${f.state ?? ""}`],
    ["Coordinates", `${f.lat.toFixed(4)}, ${f.lon.toFixed(4)}`], ["Title V permit", f.title_v_permit], ["NSR", f.nsr_authorization],
    ["Regulated entity", f.regulated_entity_number], ["Capacity", f.design_capacity_mmscfd ? `${f.design_capacity_mmscfd} MMscfd` : undefined],
    ["Sector", f.sector],
  ];
  return (
    <div className="space-y-3">
      <div>
        <div className="text-base font-bold text-ink">{f.name}</div>
        {f.data_status !== "cached" && <div className="mt-1 text-xs text-alert-amber">No cached observations — assessment will report a data gap.</div>}
      </div>
      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
        {rows.filter(([, v]) => v).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <AvailabilityChips f={f} />
    </div>
  );
}

type Layers = { s2_truecolor: boolean; s2_swir: boolean; plume: boolean; firms: boolean };

export function SiteMap({ f, run }: { f: Facility; run: RunState }) {
  const [layers, setLayers] = useState<Layers>({ s2_truecolor: false, s2_swir: false, plume: true, firms: true });
  const [plume, setPlume] = useState<{ lat: number[]; lon: number[]; v: number[] } | null>(null);
  const [firms, setFirms] = useState<{ lat: number[]; lon: number[]; text: string[] } | null>(null);
  const [images, setImages] = useState<Record<string, any>>({});
  const toolsDone = useMemo(() => new Set(run.events.filter((e) => e.type === "tool_result" && e.status === "ok").map((e) => e.name)), [run.events]);
  const imagesSeen = useMemo(() => new Set(run.events.filter((e) => e.type === "omni_analysis" && e.tool === "analyze_image").map((e) => e.target_id)), [run.events]);

  useEffect(() => { setPlume(null); setFirms(null); setImages({}); }, [run.runId]);
  useEffect(() => {
    if (run.runId && toolsDone.has("plume_map") && !plume)
      fetchCsv(runFileUrl(run.runId, "evidence/emit_plume_pixels.csv")).then(({ rows }) =>
        setPlume({ lat: rows.map((r) => +r.lat), lon: rows.map((r) => +r.lon), v: rows.map((r) => +r.enh_ppm_m) })).catch(() => {});
  }, [toolsDone, run.runId, plume]);
  useEffect(() => {
    if (run.runId && toolsDone.has("flare_activity") && !firms)
      fetchCsv(runFileUrl(run.runId, "evidence/firms_subset.csv")).then(({ rows }) =>
        setFirms({ lat: rows.map((r) => +r.latitude), lon: rows.map((r) => +r.longitude),
          text: rows.map((r) => `${r.acq_date} ${String(r.acq_time).padStart(4, "0")} UTC · ${r.satellite} · FRP ${r.frp} MW`) })).catch(() => {});
  }, [toolsDone, run.runId, firms]);
  useEffect(() => {
    imagesSeen.forEach((id) => { if (!images[id]) api.image(id).then((m) => setImages((s) => ({ ...s, [id]: m }))).catch(() => {}); });
  }, [imagesSeen, images]);

  const data: any[] = [];
  if (plume && layers.plume)
    data.push({ type: "scattermapbox", lat: plume.lat, lon: plume.lon, mode: "markers", name: "Plume mask pixels",
      marker: { size: 6, color: "#d95926", opacity: 0.75 }, hovertemplate: "%{text} ppm·m<extra>plume pixel</extra>", text: plume.v.map((x) => x.toFixed(0)) });
  if (firms && layers.firms)
    data.push({ type: "scattermapbox", lat: firms.lat, lon: firms.lon, mode: "markers", name: "FIRMS ≤1.5 km",
      marker: { size: 11, color: "#fab219" }, text: firms.text, hovertemplate: "%{text}<extra>VIIRS</extra>" });
  data.push({ type: "scattermapbox", lat: [f.lat], lon: [f.lon], mode: "markers", name: f.name,
    marker: { size: 14, color: "#1b1b1b" }, hovertemplate: `${f.name}<extra></extra>` });
  const mapLayers: any[] = [];
  (["s2_truecolor", "s2_swir"] as const).forEach((id) => {
    const m = images[id];
    if (m && layers[id]) {
      const b = m.bounds;
      mapLayers.push({ sourcetype: "image", source: window.location.origin + m.url, opacity: 0.85, below: "traces",
        coordinates: [[b.west, b.north], [b.east, b.north], [b.east, b.south], [b.west, b.south]] });
    }
  });
  const fig = {
    data,
    layout: {
      mapbox: { style: "open-street-map", center: { lat: f.lat + 0.015, lon: f.lon }, zoom: f.data_status === "cached" ? 11.3 : 9, layers: mapLayers },
      margin: { l: 0, r: 0, t: 0, b: 0 }, paper_bgcolor: "#ffffff", showlegend: false,
    },
  };
  const toggles: [keyof Layers, string, boolean][] = [
    ["plume", "Plume mask", !!plume], ["firms", "FIRMS detections", !!firms],
    ["s2_truecolor", "Sentinel-2 true colour", !!images.s2_truecolor], ["s2_swir", "Sentinel-2 SWIR", !!images.s2_swir],
  ];
  return (
    <div className="space-y-2">
      <div className="border border-rule"><Plot figure={fig} height={340} /></div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
        {toggles.map(([k, label, avail]) => (
          <label key={k} className={`flex items-center gap-1 ${avail ? "" : "opacity-40"}`} title={avail ? "" : "appears when the agent uses this data"}>
            <input type="checkbox" disabled={!avail} checked={layers[k]} onChange={(e) => setLayers((s) => ({ ...s, [k]: e.target.checked }))} />
            {label}
          </label>
        ))}
      </div>
      {(layers.s2_truecolor && images.s2_truecolor) || (layers.s2_swir && images.s2_swir) ? (
        <p className="text-[11px] text-alert-amber">Sentinel-2 layers are 2026-09-18 regional screenshots with approximate bounds — context only.</p>
      ) : null}
    </div>
  );
}
