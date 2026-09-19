import { createContext, ReactNode, useContext, useState } from "react";

/** Traceability: a clicked verdict number highlights the ledger records and tool calls it came from. */
export interface TraceSel { label: string; evidenceIds: string[]; callIds: string[] }
const Ctx = createContext<{ sel: TraceSel | null; setSel: (s: TraceSel | null) => void }>({ sel: null, setSel: () => {} });

export function TraceProvider({ children }: { children: ReactNode }) {
  const [sel, setSel] = useState<TraceSel | null>(null);
  return <Ctx.Provider value={{ sel, setSel }}>{children}</Ctx.Provider>;
}
export const useTrace = () => useContext(Ctx);
