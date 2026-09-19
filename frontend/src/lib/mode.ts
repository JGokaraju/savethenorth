import { useCallback, useEffect, useState } from "react";

export type RunMode = "demo" | "live";
const KEY = "stn-mode";

/** Demo vs Live, remembered per browser. Live is only selectable when the backend has keys. */
export function useRunMode(liveAvailable: boolean | undefined) {
  const [mode, setModeState] = useState<RunMode>(() => {
    try { return (localStorage.getItem(KEY) as RunMode) || "demo"; } catch { return "demo"; }
  });
  useEffect(() => { if (liveAvailable === false && mode === "live") setModeState("demo"); }, [liveAvailable, mode]);
  const setMode = useCallback((m: RunMode) => {
    setModeState(m);
    try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
  }, []);
  return { mode: liveAvailable ? mode : "demo", setMode };
}
