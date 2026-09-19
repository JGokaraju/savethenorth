import { createContext, ReactNode, useCallback, useContext, useState } from "react";

type Toast = { id: number; msg: string; kind: "error" | "info" };
const Ctx = createContext<(msg: string, kind?: "error" | "info") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((msg: string, kind: "error" | "info" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 7000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} role="status"
            className={`pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-xl backdrop-blur ${t.kind === "error" ? "border-red-200 bg-white text-red-700" : "border-slate-200 bg-white text-slate-700"}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
