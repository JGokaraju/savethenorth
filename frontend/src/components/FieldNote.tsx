import { useEffect, useRef, useState } from "react";
import { api, FieldNote as Note } from "../lib/api";
import { Spinner } from "./ui";

type Phase = "idle" | "recording" | "sending" | "done" | "error";
const MAX_MS = 20000;

/** Field mode: hold the button, ask out loud, and OMNI answers from the recording plus the site view.
 *  The desk assessment never calls this — it is for someone standing at the facility. */
export function FieldNote({ facilityId, context }: { facilityId: string; context?: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState<Note | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [secs, setSecs] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<BlobPart[]>([]);
  const timer = useRef<number>();
  const stop = useRef<number>();

  useEffect(() => () => {
    window.clearInterval(timer.current);
    window.clearTimeout(stop.current);
    rec.current?.stream.getTracks().forEach((t) => t.stop());
  }, []);

  const send = async (clip: Blob) => {
    setPhase("sending");
    try {
      setNote(await api.fieldNote(facilityId, clip, context));
      setPhase("done");
    } catch (e: any) {
      setErr(e.message ?? String(e));
      setPhase("error");
    }
  };

  const start = async () => {
    setErr(null); setNote(null); setSecs(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        window.clearInterval(timer.current);
        send(new Blob(chunks.current, { type: "audio/webm" }));
      };
      rec.current = mr;
      mr.start();
      setPhase("recording");
      timer.current = window.setInterval(() => setSecs((s) => s + 1), 1000);
      stop.current = window.setTimeout(() => mr.state !== "inactive" && mr.stop(), MAX_MS);
    } catch (e: any) {
      setErr(e?.name === "NotAllowedError" ? "Microphone permission denied." : (e.message ?? String(e)));
      setPhase("error");
    }
  };

  const halt = () => {
    window.clearTimeout(stop.current);
    if (rec.current?.state !== "inactive") rec.current?.stop();
  };

  return (
    <div className="border border-rule">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule bg-panel px-4 py-3">
        <div>
          <p className="text-[15px] font-bold text-ink">Field mode — ask from the site</p>
          <p className="text-xs text-muted">
            Your spoken question and the aerial view go to Huawei OMNI together. Qualitative answers only: the numbers
            stay with the satellite analysis.
          </p>
        </div>
        {phase === "recording"
          ? <button className="btn-dark" onClick={halt}>Stop · {secs}s</button>
          : <button className="btn-light" onClick={start} disabled={phase === "sending"}>
              {phase === "sending" ? <><Spinner /> Listening…</> : "Hold a question"}
            </button>}
      </div>
      <div className="px-4 py-3 text-sm">
        {phase === "idle" && <p className="text-muted">Press record, ask something like “what am I looking at, and did this operator report anything this month?”</p>}
        {phase === "recording" && <p className="text-ink">Recording — press stop when you have finished the question (cuts off at {MAX_MS / 1000}s).</p>}
        {phase === "sending" && <p className="text-muted">Sending the clip and the site view to OMNI…</p>}
        {phase === "error" && <p className="text-alert-red">{err}</p>}
        {phase === "done" && note && (
          <div className="space-y-2">
            <p className="whitespace-pre-wrap text-ink">{note.answer}</p>
            <p className="text-[11px] uppercase tracking-[0.12em] text-muted">
              {note.model} · {note.mode} · modalities: {note.modalities.join(" + ")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
