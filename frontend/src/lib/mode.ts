import { useCallback, useEffect, useState } from "react";

export type RunMode = "demo" | "live";
const KEY = "stn-mode";

/** Live by default, remembered per browser; falls back to demo when the backend has no keys. */
export function useRunMode(liveAvailable: boolean | undefined) {
  const [mode, setModeState] = useState<RunMode>(() => {
    try { return (localStorage.getItem(KEY) as RunMode) || "live"; } catch { return "live"; }
  });
  useEffect(() => { if (liveAvailable === false && mode === "live") setModeState("demo"); }, [liveAvailable, mode]);
  const setMode = useCallback((m: RunMode) => {
    setModeState(m);
    try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
  }, []);
  return { mode: liveAvailable === false ? "demo" : mode, setMode };
}
