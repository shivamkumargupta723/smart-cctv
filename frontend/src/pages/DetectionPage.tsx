import { useRef, useState } from "react";
import { RefreshCw, Plus, Trash2, Check, X, Undo2, Shapes } from "lucide-react";
import { post } from "../api";
import { useLive } from "../live";
import { Card, PageHeader, FieldList, SaveBar, useSection, useFlash, Toggle, Badge, type Field } from "../components/ui";
import { LiveStream } from "../components/shared";

type Zone = { id: string; name: string; type: "detect" | "ignore"; points: number[][]; enabled: boolean };

const CATEGORY_FIELDS: Field[] = [
  { key: "enabled", label: "AI detection enabled", type: "toggle", help: "Master switch for YOLO object detection" },
  { key: "detect_persons", label: "Person detection", type: "toggle" },
  { key: "detect_faces", label: "Face detection", type: "toggle", help: "Locates faces inside detected people (no identity recognition)" },
  { key: "detect_vehicles", label: "Vehicle detection", type: "toggle", help: "car, bus, truck, motorcycle, bicycle, boat…" },
  { key: "detect_animals", label: "Animal detection", type: "toggle", help: "dog, cat, bird, horse, cow…" },
  { key: "detect_objects", label: "Other object detection", type: "toggle", help: "All remaining COCO classes (backpack, bottle, phone…)" },
];
const PRESENCE_FIELDS: Field[] = [
  { key: "person_confirm_frames", label: "Frames to confirm a person", type: "number", min: 1, max: 10, help: "Higher = fewer false alerts, slightly slower" },
  { key: "exit_timeout_seconds", label: "Exit timeout", type: "number", min: 1, max: 30, step: 0.5, unit: "sec", help: "Person counted as left after not being seen this long" },
  { key: "loiter_seconds", label: "Loitering alert after", type: "number", min: 5, max: 3600, unit: "sec", help: "Alert when a person remains in view this long" },
];
const MOTION_FIELDS: Field[] = [
  { key: "motion_enabled", label: "Motion detection", type: "toggle" },
  { key: "motion_sensitivity", label: "Motion sensitivity", type: "range", min: 1, max: 100, help: "Higher detects smaller changes" },
  { key: "motion_min_area", label: "Minimum motion area", type: "range", min: 0.001, max: 0.1, step: 0.001, fmt: (v) => `${(v * 100).toFixed(1)}%`, help: "Ignore motion smaller than this share of the frame" },
];

export default function DetectionPage() {
  const s = useSection<any>("detection");
  const { live, status } = useLive();
  const flash = useFlash();
  const classes = status?.detector.classes || [];

  const alertObjs: string[] = s.draft?.alert_objects || [];
  const toggleAlert = (c: string) => s.set("alert_objects", alertObjs.includes(c) ? alertObjs.filter((x) => x !== c) : [...alertObjs, c]);

  return (
    <div>
      <PageHeader title="AI Detection" subtitle="What the AI looks for, where it looks, and what triggers alerts" />
      <div className="grid gap-5 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-5">
          {s.data && <ZoneEditor zones={s.data.zones || []} onSaved={() => flash("ok", "Zones saved")} />}
          <Card title="Live detections" actions={<Badge tone="signal">{live?.detections.length ?? 0}</Badge>}>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="py-1">Track</th><th>Label</th><th>Category</th><th className="text-right">Confidence</th></tr></thead>
                <tbody>
                  {(live?.detections || []).map((d, i) => (
                    <tr key={i} className="border-t border-ink-800">
                      <td className="mono py-1.5 text-slate-500">{d.track_id ? `#${d.track_id}` : "—"}</td>
                      <td className="text-slate-200">{d.label}</td>
                      <td><Badge tone={d.category === "person" ? "signal" : d.category === "face" ? "info" : "default"}>{d.category}</Badge></td>
                      <td className="mono text-right text-slate-300">{(d.confidence * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!live?.detections.length && <div className="py-6 text-center text-xs text-slate-500">No objects in view right now</div>}
            </div>
          </Card>
        </div>
        <div className="space-y-5">
          <Card title="Detection types">{s.draft && <FieldList fields={CATEGORY_FIELDS} draft={s.draft} set={s.set} />}</Card>
          <Card title="Person presence · entry / exit">{s.draft && <FieldList fields={PRESENCE_FIELDS} draft={s.draft} set={s.set} />}</Card>
          <Card title="Motion">{s.draft && <FieldList fields={MOTION_FIELDS} draft={s.draft} set={s.set} />}
            <p className="mt-2 text-xs text-slate-500">Motion alone never starts a person event — the AI must confirm a human first. Motion-only events are logged separately.</p>
          </Card>
          <Card title="Alert & record on these objects" actions={<Badge>{alertObjs.length} selected</Badge>}>
            <p className="mb-3 text-xs text-slate-500">People always trigger alerts. Pick extra objects that should trigger an alert, a photo and an event recording.</p>
            <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
              {classes.filter((c) => c !== "person").map((c) => (
                <button key={c} onClick={() => toggleAlert(c)} className={`rounded-md px-2 py-1 text-xs transition ${alertObjs.includes(c) ? "bg-signal text-ink-950" : "bg-ink-850 text-slate-300 hover:bg-ink-700"}`}>{c}</button>
              ))}
            </div>
          </Card>
        </div>
      </div>
      <SaveBar dirty={s.dirty} saving={s.saving} onSave={() => s.save({ ...s.draft, zones: undefined })} onReset={s.reset} />
    </div>
  );
}

function ZoneEditor({ zones, onSaved }: { zones: Zone[]; onSaved: () => void }) {
  const [base, setBase] = useState<Zone[]>(zones);
  const [list, setList] = useState<Zone[]>(zones);
  const [drawing, setDrawing] = useState<number[][] | null>(null);
  const [newType, setNewType] = useState<"detect" | "ignore">("detect");
  const [newName, setNewName] = useState("");
  const [frameKey, setFrameKey] = useState(Date.now());
  const [useLiveView, setUseLiveView] = useState(false);
  const svg = useRef<SVGSVGElement>(null);
  const flash = useFlash();
  const { status } = useLive();
  const dirty = JSON.stringify(list) !== JSON.stringify(base);

  const click = (e: React.MouseEvent) => {
    if (!drawing || !svg.current) return;
    const r = svg.current.getBoundingClientRect();
    setDrawing([...drawing, [+((e.clientX - r.left) / r.width).toFixed(4), +((e.clientY - r.top) / r.height).toFixed(4)]]);
  };
  const finish = () => {
    if (!drawing || drawing.length < 3) return flash("err", "A zone needs at least 3 points");
    setList([...list, { id: `z${Date.now()}`, name: newName || `${newType === "ignore" ? "Ignore" : "Detect"} zone ${list.length + 1}`, type: newType, points: drawing, enabled: true }]);
    setDrawing(null);
    setNewName("");
  };
  const save = async () => {
    try { const r = await post("/api/models/zones", { zones: list }); setBase(r.zones); setList(r.zones); onSaved(); } catch (e: any) { flash("err", e.message); }
  };
  const pts = (p: number[][]) => p.map(([x, y]) => `${x * 1000},${y * 562.5}`).join(" ");

  return (
    <Card title={<span className="flex items-center gap-2"><Shapes size={15} /> Detection & ignore zones</span>}
      actions={<>
        <label className="flex items-center gap-2 text-xs text-slate-400">Live <Toggle checked={useLiveView} onChange={setUseLiveView} /></label>
        <button className="btn-ghost py-1 text-xs" onClick={() => setFrameKey(Date.now())}><RefreshCw size={13} /> Frame</button>
      </>}>
      <div className="relative overflow-hidden rounded-lg bg-black">
        {useLiveView ? <LiveStream overlay={false} paused={status?.camera.paused} connected={status?.camera.connected} className="rounded-none" />
          : <img src={`/api/frame.jpg?k=${frameKey}`} className="aspect-video w-full object-contain" alt="Camera frame" onError={(e) => (e.currentTarget.style.opacity = "0.1")} />}
        <svg ref={svg} viewBox="0 0 1000 562.5" preserveAspectRatio="none" className={`absolute inset-0 h-full w-full ${drawing ? "cursor-crosshair" : ""}`} onClick={click}>
          {list.filter((z) => z.enabled).map((z) => (
            <g key={z.id}>
              <polygon points={pts(z.points)} fill={z.type === "ignore" ? "rgba(239,68,68,.18)" : "rgba(34,197,94,.15)"} stroke={z.type === "ignore" ? "#ef4444" : "#22c55e"} strokeWidth="2.5" />
              <text x={z.points[0][0] * 1000 + 6} y={z.points[0][1] * 562.5 + 20} fill={z.type === "ignore" ? "#fca5a5" : "#86efac"} fontSize="18" fontWeight="600">{z.name}</text>
            </g>
          ))}
          {drawing && (
            <g>
              <polyline points={pts(drawing)} fill={newType === "ignore" ? "rgba(239,68,68,.2)" : "rgba(245,165,36,.2)"} stroke="#f5a524" strokeWidth="2.5" strokeDasharray="8 5" />
              {drawing.map(([x, y], i) => <circle key={i} cx={x * 1000} cy={y * 562.5} r="6" fill="#f5a524" />)}
            </g>
          )}
        </svg>
        {drawing && <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-black/75 px-2.5 py-1 text-xs text-signal">Click on the image to add points · {drawing.length} placed</div>}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!drawing ? (
          <>
            <select className="input w-40" value={newType} onChange={(e) => setNewType(e.target.value as any)}>
              <option value="detect">Detection zone</option><option value="ignore">Ignore zone</option>
            </select>
            <input className="input w-44" placeholder="Zone name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <button className="btn-ghost" onClick={() => setDrawing([])}><Plus size={15} /> Draw zone</button>
          </>
        ) : (
          <>
            <button className="btn-primary" onClick={finish}><Check size={15} /> Finish</button>
            <button className="btn-ghost" onClick={() => setDrawing(drawing.slice(0, -1))} disabled={!drawing.length}><Undo2 size={15} /> Undo point</button>
            <button className="btn-ghost" onClick={() => setDrawing(null)}><X size={15} /> Cancel</button>
          </>
        )}
        <button className="btn-primary ml-auto" disabled={!dirty} onClick={save}><Check size={15} /> Save zones</button>
      </div>

      <div className="mt-3 space-y-1.5">
        {list.map((z, i) => (
          <div key={z.id} className="flex items-center gap-3 rounded-md bg-ink-850 px-3 py-2 text-sm">
            <span className={`h-2.5 w-2.5 rounded-sm ${z.type === "ignore" ? "bg-red-500" : "bg-emerald-500"}`} />
            <input className="min-w-0 flex-1 bg-transparent text-slate-200 outline-none" value={z.name} onChange={(e) => setList(list.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <Badge tone={z.type === "ignore" ? "bad" : "good"}>{z.type}</Badge>
            <Toggle checked={z.enabled} onChange={(v) => setList(list.map((x, j) => (j === i ? { ...x, enabled: v } : x)))} />
            <button className="text-slate-500 hover:text-red-400" onClick={() => setList(list.filter((_, j) => j !== i))}><Trash2 size={15} /></button>
          </div>
        ))}
        {!list.length && <p className="text-xs text-slate-500">No zones — the whole frame is monitored. Detection zones limit alerts to an area (e.g. your door); ignore zones mask things like trees, TVs or a road.</p>}
      </div>
    </Card>
  );
}
