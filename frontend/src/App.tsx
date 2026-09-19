import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/Toasts";

const Landing = lazy(() => import("./pages/Landing"));
const Workspace = lazy(() => import("./pages/Workspace"));

export default function App() {
  return (
    <ToastProvider>
      <Suspense fallback={<div className="flex h-screen items-center justify-center text-slate-500">Loading…</div>}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/assess/:facilityId" element={<Workspace />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}
