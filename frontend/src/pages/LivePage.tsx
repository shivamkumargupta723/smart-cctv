import { useRef, useState } from "react";
import { Camera, Maximize2, Pause, Play, Users, Gauge, Cpu, Sun, Moon, Circle, Layers, Activity, RefreshCw } from "lucide-react";
import { post, fmtBytes } from "../api";
import { useLive } from "../live";
import { Card, Stat, Toggle, useFlash, Badge, Empty } from "../components/ui";
import { EventItem, LiveStream } from "../components/shared";
import EventDetail from "./EventDetail";

export default function LivePage() {
  const { status, live, events, refresh } = useLive();
  const [overlay, setOverlay] = useState(true);
  const [busy, setBusy] = useState(false);
  const [openEvent, setOpenEvent] = useState<number | null>(null);
  const flash = useFlash();
  const box = useRef<HTMLDivElement>(null);
  const rec = status?.recording;
  const cam = status?.camera;

  const control = async (body: any, msg: string) => {
    setBusy(true);
    try {
      await post("/api/recording/control", body);
      flash("ok", msg);
      refresh();
    } catch (e: any) {
      flash("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const snap = async () => {
    try {
      await post("/api/snapshots/capture");
      flash("ok", "Snapshot saved to gallery");
    } catch (e: any) {
      flash("err", e.message);
    }
  };
  const counts = (live?.detections || []).reduce<Record<string, number>>((a, d) => ((a[d.category] = (a[d.category] || 0) + 1), a), {});

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
      <div className="space-y-5">
        <Card pad={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-700 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-white">Live Camera</span>
              <span className="mono text-xs text-slate-500">{cam?.source} · {cam?.width}×{cam?.height}</span>
            </div>
            <div className="flex items-center gap-2">
              <button className={`btn-ghost py-1.5 ${overlay ? "!border-signal/50 text-signal" : ""}`} onClick={() => setOverlay(!overlay)}><Layers size={15} /> AI overlay</button>
              <button className="btn-ghost py-1.5" onClick={snap} disabled={!cam?.connected}><Camera size={15} /> Snapshot</button>
              <button className="btn-ghost py-1.5" onClick={() => box.current?.requestFullscreen()}><Maximize2 size={15} /></button>
            </div>
          </div>
          <div ref={box} className="relative bg-black">
            <LiveStream overlay={overlay} paused={cam?.paused} connected={cam?.connected} className="rounded-none" />
            <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-1.5">
              {rec?.recording && <span className="chip bg-red-600/90 text-white"><Circle size={8} className="rec-dot fill-white" /> REC</span>}
              {live?.night && <span className="chip bg-indigo-600/80 text-white"><Moon size={11} /> Night mode</span>}
              {live?.motion && <span className="chip bg-sky-600/80 text-white"><Activity size={11} /> Motion</span>}
              {(live?.persons ?? 0) > 0 && <span className="chip bg-amber-500/90 text-black"><Users size={11} /> {live?.persons} person{live!.persons > 1 ? "s" : ""}</span>}
            </div>
          </div>
          <div className="grid gap-3 border-t border-ink-700 p-4 sm:grid-cols-3">
            <ControlRow label="Privacy pause" hint="Turns camera & all recording off" on={!!rec?.paused} disabled={busy}
              onChange={(v) => control({ paused: v }, v ? "Privacy pause enabled — camera off" : "Monitoring resumed")} icon={rec?.paused ? <Play size={15} /> : <Pause size={15} />} />
            <ControlRow label="Continuous recording" hint="24/7 segmented footage" on={!!rec?.continuous_enabled} disabled={busy || !!rec?.paused}
              onChange={(v) => control({ continuous_enabled: v }, v ? "Continuous recording on" : "Continuous recording off")} />
            <ControlRow label="Smart event recording" hint="Record when people/objects appear" on={!!rec?.event_enabled} disabled={busy || !!rec?.paused}
              onChange={(v) => control({ event_enabled: v }, v ? "Event recording on" : "Event recording off")} />
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="People in view" value={live?.persons ?? 0} tone={(live?.persons ?? 0) > 0 ? "signal" : "default"} icon={<Users size={16} />}
            sub={live?.active_event ? `Event #${live.active_event} in progress` : "No active event"} />
          <Stat label="Camera FPS" value={cam?.fps.toFixed(1) ?? "—"} icon={<Gauge size={16} />} sub={`Stream ${status?.engine.stream_fps ?? 0} fps`} />
          <Stat label="AI inference" value={`${live?.inference_ms?.toFixed(0) ?? "—"} ms`} icon={<Cpu size={16} />} sub={`${live?.processing_fps ?? 0} fps on ${status?.detector.device ?? "—"}`} />
          <Stat label="Lighting" value={live?.night ? "Night" : "Day"} icon={live?.night ? <Moon size={16} /> : <Sun size={16} />} sub={`Brightness ${live?.brightness ?? 0}`} />
        </div>
      </div>

      <div className="space-y-5">
        <Card title="Detected now" actions={<Badge tone="signal">{live?.detections.length ?? 0} objects</Badge>}>
          <div className="mb-3 grid grid-cols-5 gap-2 text-center">
            {["person", "face", "vehicle", "animal", "object"].map((c) => (
              <div key={c} className="rounded-lg bg-ink-850 py-2">
                <div className="mono text-lg font-semibold text-white">{counts[c] || 0}</div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{c}</div>
              </div>
            ))}
          </div>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {(live?.detections || []).filter((d) => d.category !== "face").slice(0, 12).map((d, i) => (
              <div key={i} className="flex items-center justify-between rounded-md bg-ink-850 px-2.5 py-1.5 text-sm">
                <span className="text-slate-200">{d.track_id ? <span className="mono mr-1.5 text-slate-500">#{d.track_id}</span> : null}{d.label}</span>
                <span className="mono text-xs text-slate-400">{(d.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
            {!live?.detections.length && <div className="py-3 text-center text-xs text-slate-500">Nothing detected</div>}
          </div>
        </Card>

        <Card title="Latest events" actions={<a href="#/events" className="text-xs text-signal hover:underline">View all</a>} pad={false}>
          <div className="max-h-[420px] overflow-y-auto p-2">
            {events.length ? events.slice(0, 15).map((e) => <EventItem key={e.id} e={e} onClick={() => setOpenEvent(e.id)} />)
              : <Empty title="No events yet" hint="Events appear here as soon as the AI detects activity." />}
          </div>
        </Card>

        <Card title="System" actions={<button className="text-slate-500 hover:text-white" onClick={refresh}><RefreshCw size={14} /></button>}>
          <dl className="space-y-2 text-sm">
            <Row k="Storage free" v={`${fmtBytes(status?.storage.disk_free)} / ${fmtBytes(status?.storage.disk_total)}`} bad={status?.storage.low} />
            <Row k="CCTV data" v={fmtBytes(status?.storage.cctv_total)} />
            <Row k="AI model" v={`${status?.detector.model} (${status?.detector.device})`} />
            <Row k="Notifications" v={Object.entries(status?.notifications || {}).filter(([, c]) => c.enabled).map(([k]) => k).join(", ") || "none"} />
            <Row k="CPU / Memory" v={`${status?.cpu_percent ?? 0}% / ${status?.mem_percent ?? 0}%`} />
          </dl>
        </Card>
      </div>
      <EventDetail id={openEvent} onClose={() => setOpenEvent(null)} />
    </div>
  );
}

function ControlRow({ label, hint, on, onChange, disabled, icon }: { label: string; hint: string; on: boolean; onChange: (v: boolean) => void; disabled?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-ink-850 px-3 py-2.5">
      <div>
        <div className="flex items-center gap-1.5 text-sm text-slate-200">{icon}{label}</div>
        <div className="text-[11px] text-slate-500">{hint}</div>
      </div>
      <Toggle checked={on} onChange={onChange} disabled={disabled} />
    </div>
  );
}

function Row({ k, v, bad }: { k: string; v: React.ReactNode; bad?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{k}</dt>
      <dd className={`mono truncate text-right text-xs leading-5 ${bad ? "text-red-400" : "text-slate-200"}`}>{v}</dd>
    </div>
  );
}
