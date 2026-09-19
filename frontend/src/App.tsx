import { useEffect, useState } from "react";

type Health = { mode: Record<string, boolean>; assets: Record<string, string> };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Plumewatch — Satellite Emissions Verification</h1>
      <p className="mt-2 text-slate-400">App shell. Landing page and workspace arrive in milestones 5 and 5b.</p>
      <pre className="mt-6 rounded bg-slate-900 p-4 text-xs">{health ? JSON.stringify(health, null, 2) : "backend not reachable"}</pre>
    </main>
  );
}
