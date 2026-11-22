import { useEffect, useState } from "react";
import { Trash2, RefreshCw, HardDrive } from "lucide-react";
import { get, post, fmtBytes, fmtTime } from "../api";
import { Card, PageHeader, FieldList, SaveBar, useSection, useFlash, Spinner, Stat, type Field } from "../components/ui";

const RETENTION: Field[] = [
  { key: "retention_continuous_days", label: "Keep continuous recordings", type: "number", min: 0, max: 3650, unit: "days", help: "0 = keep forever" },
  { key: "retention_events_days", label: "Keep event recordings & history", type: "number", min: 0, max: 3650, unit: "days" },
  { key: "retention_snapshots_days", label: "Keep photos", type: "number", min: 0, max: 3650, unit: "days" },
  { key: "min_free_gb", label: "Always keep free", type: "number", min: 1, max: 2000, unit: "GB", help: "Oldest continuous footage is deleted first when free space drops below this" },
  { key: "low_storage_alert_gb", label: "Low-storage alert below", type: "number", min: 1, max: 2000, unit: "GB" },
  { key: "auto_cleanup", label: "Automatic hourly cleanup", type: "toggle" },
];
const RECORDING: Field[] = [
  { key: "segment_minutes", label: "Continuous segment length", type: "number", min: 1, max: 120, unit: "min" },
  { key: "record_fps", label: "Recording frame rate", type: "select", options: [5, 10, 15, 20, 25, 30].map((v) => ({ value: v, label: `${v} fps` })) },
  { key: "video_crf", label: "Video quality (CRF)", type: "range", min: 18, max: 35, help: "Lower = better quality, bigger files (23 recommended)" },
  { key: "pre_event_seconds", label: "Pre-event footage", type: "number", min: 0, max: 30, unit: "sec" },
  { key: "post_event_seconds", label: "Post-event recording", type: "number", min: 2, max: 300, unit: "sec" },
  { key: "max_event_minutes", label: "Max event clip length", type: "number", min: 1, max: 240, unit: "min", help: "Long events continue in a new clip" },
  { key: "record_on_objects", label: "Also record configured objects", type: "toggle" },
  { key: "annotate_recordings", label: "Burn AI boxes into recordings", type: "toggle" },
  { key: "snapshot_interval_seconds", label: "Photo interval during an event", type: "number", min: 2, max: 600, unit: "sec", help: "Prevents hundreds of duplicate photos" },
  { key: "max_snapshots_per_event", label: "Max photos per event", type: "number", min: 1, max: 200 },
  { key: "snapshot_quality", label: "Photo JPEG quality", type: "range", min: 60, max: 100 },
];

export default function StoragePage() {
  const ret = useSection<any>("storage");
  const rec = useSection<any>("recording");
  const [st, setSt] = useState<any>(null);
  const [cleaning, setCleaning] = useState(false);
  const flash = useFlash();
  const load = () => get("/api/storage").then(setSt);
  useEffect(() => { load(); }, []);

  const cleanup = async () => {
    setCleaning(true);
    try {
      const r = await post("/api/storage/cleanup");
      const n = Object.values(r.removed as Record<string, number>).reduce((a, b) => a + b, 0);
      flash("ok", n ? `Cleanup removed ${n} items` : "Nothing expired to clean up");
      setSt(r.stats);
    } catch (e: any) { flash("err", e.message); } finally { setCleaning(false); }
  };
  const folders = st ? Object.entries(st.folders as Record<string, number>) : [];
  const colors: Record<string, string> = { continuous: "bg-signal", events: "bg-sky-400", snapshots: "bg-emerald-400", logs: "bg-slate-400", exports: "bg-violet-400" };
  const dirty = ret.dirty || rec.dirty;

  return (
    <div>
      <PageHeader title="Storage Management" subtitle="All footage stays on this Mac — control how much is kept"
        actions={<>
          <button className="btn-ghost" onClick={load}><RefreshCw size={15} /> Refresh</button>
          <button className="btn-danger" onClick={cleanup} disabled={cleaning}>{cleaning ? <Spinner /> : <Trash2 size={15} />} Run cleanup now</button>
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Disk free" value={fmtBytes(st?.disk_free)} tone={st?.low ? "bad" : "good"} icon={<HardDrive size={16} />} sub={`of ${fmtBytes(st?.disk_total)} · ${st?.percent_used ?? 0}% used`} />
        <Stat label="CCTV data" value={fmtBytes(st?.cctv_total)} sub="recordings + photos + logs" />
        <Stat label="Recordings" value={(st?.counts.continuous ?? 0) + (st?.counts.events ?? 0)} sub={`${st?.counts.continuous ?? 0} continuous · ${st?.counts.events ?? 0} event`} />
        <Stat label="Photos" value={st?.counts.snapshots ?? 0} sub={`${st?.counts.event_rows ?? 0} events in history`} />
      </div>
      <Card title="Usage breakdown" className="mb-5">
        <div className="flex h-3 overflow-hidden rounded-full bg-ink-700">
          {folders.map(([k, v]) => <div key={k} className={colors[k]} style={{ width: `${st.cctv_total ? (v / st.cctv_total) * 100 : 0}%` }} />)}
        </div>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
          {folders.map(([k, v]) => <span key={k} className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-sm ${colors[k]}`} /><span className="capitalize text-slate-400">{k}</span><span className="mono text-slate-200">{fmtBytes(v)}</span></span>)}
        </div>
        <p className="mt-3 text-xs text-slate-500">Last cleanup: {st?.last_cleanup ? fmtTime(st.last_cleanup) : "not yet run"}</p>
      </Card>
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Retention & automatic cleanup">{ret.draft && <FieldList fields={RETENTION} draft={ret.draft} set={ret.set} />}</Card>
        <Card title="Recording & photo capture">{rec.draft && <FieldList fields={RECORDING} draft={rec.draft} set={rec.set} />}</Card>
      </div>
      <SaveBar dirty={dirty} saving={ret.saving || rec.saving}
        onSave={async () => {
          if (ret.dirty) await ret.save();
          if (rec.dirty) {
            const { paused, continuous_enabled, event_enabled, ...rest } = rec.draft; // live toggles are controlled elsewhere
            void paused; void continuous_enabled; void event_enabled;
            await rec.save(rest);
          }
        }}
        onReset={() => { ret.reset(); rec.reset(); }} />
    </div>
  );
}
