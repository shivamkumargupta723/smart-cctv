import { useEffect, useRef, useState } from "react";
import { VideoOff, Pause } from "lucide-react";
import { fmtClock, fmtDur, ago } from "../api";
import type { EventRow } from "../live";
import { Badge, EVENT_TONES } from "./ui";

export function LiveStream({ overlay = true, className = "", paused, connected }: { overlay?: boolean; className?: string; paused?: boolean; connected?: boolean }) {
  const [key, setKey] = useState(0);
  const [err, setErr] = useState(false);
  const timer = useRef<number>();
  useEffect(() => {
    setErr(false);
    setKey((k) => k + 1);
  }, [overlay, connected, paused]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const onError = () => {
    setErr(true);
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { setErr(false); setKey((k) => k + 1); }, 2500);
  };
  const offline = paused || connected === false || err;
  return (
    <div className={`scanlines relative aspect-video w-full overflow-hidden rounded-lg bg-black ${className}`}>
      {!paused && connected !== false && (
        <img key={key} src={`/api/stream?overlay=${overlay ? 1 : 0}&k=${key}`} onError={onError} onLoad={() => setErr(false)}
          className="h-full w-full object-contain" alt="Live camera" />
      )}
      {offline && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-ink-950 text-slate-500">
          {paused ? <Pause size={36} /> : <VideoOff size={36} />}
          <div className="text-sm">{paused ? "Privacy pause — camera is off" : "Camera offline — reconnecting…"}</div>
        </div>
      )}
    </div>
  );
}

export function EventItem({ e, onClick }: { e: EventRow; onClick?: () => void }) {
  const dur = e.ended_at ? e.ended_at - e.started_at : null;
  return (
    <button onClick={onClick} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-ink-800">
      <div className="h-11 w-16 shrink-0 overflow-hidden rounded-md bg-ink-800">
        {e.snapshot_id && <img src={`/api/snapshots/${e.snapshot_id}/image?thumb=1`} className="h-full w-full object-cover" loading="lazy" alt="" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Badge tone={EVENT_TONES[e.type] || "default"}>{e.type}</Badge>
          {!e.ended_at && <span className="chip bg-red-500/15 text-red-300"><span className="rec-dot h-1.5 w-1.5 rounded-full bg-red-500" />live</span>}
        </div>
        <div className="mt-0.5 truncate text-sm text-slate-200">{e.label}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className="mono text-xs text-slate-300">{fmtClock(e.started_at)}</div>
        <div className="text-[11px] text-slate-500">{dur && dur > 1 ? fmtDur(dur) : ago(e.started_at)}</div>
      </div>
    </button>
  );
}
