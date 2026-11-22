import { useEffect, useState } from "react";
import { Plug, Search, KeyRound, Network } from "lucide-react";
import { get, post } from "../api";
import { Card, PageHeader, FieldList, SaveBar, useSection, useFlash, Badge, Spinner, type Field } from "../components/ui";
import { useLive } from "../live";
import { LiveStream } from "../components/shared";

const FIELDS: Field[] = [
  { key: "name", label: "Camera name", type: "text", help: "Shown in alerts and timestamps" },
  { key: "width", label: "Resolution", type: "select", options: [{ value: 640, label: "640 × 480" }, { value: 1280, label: "1280 × 720 (HD)" }, { value: 1920, label: "1920 × 1080 (Full HD)" }, { value: 2560, label: "2560 × 1440" }, { value: 3840, label: "3840 × 2160 (4K)" }] },
  { key: "fps", label: "Capture frame rate", type: "select", options: [10, 15, 20, 24, 30, 60].map((v) => ({ value: v, label: `${v} fps` })) },
  { key: "flip_horizontal", label: "Mirror image", type: "toggle" },
  { key: "rotate", label: "Rotation", type: "select", options: [0, 90, 180, 270].map((v) => ({ value: v, label: `${v}°` })) },
  { key: "reconnect_seconds", label: "Reconnect retry interval", type: "number", min: 1, max: 60, unit: "sec", help: "Automatic reconnect when the camera disconnects" },
];
const HEIGHTS: Record<number, number> = { 640: 480, 1280: 720, 1920: 1080, 2560: 1440, 3840: 2160 };

export default function CameraPage() {
  const s = useSection<any>("camera");
  const srv = useSection<any>("server");
  const { status } = useLive();
  const flash = useFlash();
  const [cams, setCams] = useState<any[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [custom, setCustom] = useState("");
  const [pw, setPw] = useState({ current: "", new: "", confirm: "" });
  const cam = status?.camera;

  const scan = async () => {
    setScanning(true);
    try { setCams((await get("/api/cameras")).cameras); } catch (e: any) { flash("err", e.message); } finally { setScanning(false); }
  };
  useEffect(() => { scan(); }, []);
  useEffect(() => {
    const src = s.data?.source;
    if (src && src !== "auto" && !/^\d+$/.test(String(src))) setCustom(String(src));
  }, [s.data?.source]);

  const set = (k: string, v: any) => {
    s.set(k, v);
    if (k === "width") s.set("height", HEIGHTS[v] || 720);
  };
  const reconnect = async () => { await post("/api/camera/reconnect"); flash("ok", "Reconnecting camera…"); };
  const changePw = async () => {
    if (pw.new !== pw.confirm) return flash("err", "New passwords do not match");
    try { await post("/api/auth/password", { current: pw.current, new: pw.new }); flash("ok", "Password changed"); setPw({ current: "", new: "", confirm: "" }); } catch (e: any) { flash("err", e.message); }
  };
  const src = String(s.draft?.source ?? "auto");
  const srcMode = src === "auto" ? "auto" : /^\d+$/.test(src) ? src : "custom";

  return (
    <div>
      <PageHeader title="Camera Settings" subtitle="USB webcam selection, image and connection settings"
        actions={<button className="btn-ghost" onClick={reconnect}><Plug size={15} /> Reconnect camera</button>} />
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="space-y-5">
          <Card pad={false}><LiveStream overlay={false} paused={cam?.paused} connected={cam?.connected} className="rounded-xl" /></Card>
          <Card title="Status">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Info k="State" v={<Badge tone={cam?.connected ? "good" : "bad"}>{cam?.paused ? "paused" : cam?.connected ? "connected" : "offline"}</Badge>} />
              <Info k="Source" v={cam?.source} />
              <Info k="Resolution" v={cam?.width ? `${cam.width}×${cam.height}` : "—"} />
              <Info k="FPS" v={cam?.fps?.toFixed(1)} />
            </div>
            {cam?.error && <div className="mt-3 rounded-md bg-red-500/10 p-2 text-xs text-red-300">{cam.error}</div>}
          </Card>
          <Card title={<span className="flex items-center gap-2"><KeyRound size={15} /> Dashboard password</span>}>
            <div className="grid gap-2 sm:grid-cols-3">
              <input className="input" type="password" placeholder="Current" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" />
              <input className="input" type="password" placeholder="New (8+ chars)" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} autoComplete="new-password" />
              <input className="input" type="password" placeholder="Confirm new" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} autoComplete="new-password" />
            </div>
            <button className="btn-ghost mt-3" disabled={!pw.current || pw.new.length < 8} onClick={changePw}>Change password</button>
          </Card>
        </div>
        <div className="space-y-5">
          <Card title="Video source" actions={<button className="btn-ghost py-1 text-xs" onClick={scan} disabled={scanning}>{scanning ? <Spinner size={13} /> : <Search size={13} />} Scan</button>}>
            <div className="space-y-2">
              <SourceOpt active={srcMode === "auto"} onClick={() => s.set("source", "auto")} title="Automatic" sub="Prefers an external USB webcam over the built-in camera" />
              {(cams || []).map((c) => (
                <SourceOpt key={c.index} active={srcMode === String(c.index)} onClick={() => s.set("source", String(c.index))}
                  title={c.name} sub={`Device index ${c.index}${c.width ? ` · ${c.width}×${c.height}` : ""}${cam?.index === c.index ? " · in use" : ""}`} />
              ))}
              {cams && !cams.length && <p className="text-xs text-slate-500">No cameras found. Plug in the USB webcam and press Scan. On macOS, allow Camera access for Terminal in System Settings → Privacy & Security → Camera.</p>}
              <div className={`rounded-lg border p-3 ${srcMode === "custom" ? "border-signal/60 bg-signal/5" : "border-ink-700 bg-ink-850"}`}>
                <div className="mb-2 text-sm text-slate-200">Network camera URL (optional)</div>
                <div className="flex gap-2">
                  <input className="input mono text-xs" placeholder="rtsp://user:pass@192.168.1.20:554/stream" value={custom} onChange={(e) => setCustom(e.target.value)} />
                  <button className="btn-ghost" disabled={!custom} onClick={() => s.set("source", custom.trim())}>Use</button>
                </div>
              </div>
            </div>
          </Card>
          <Card title="Image">{s.draft && <FieldList fields={FIELDS} draft={s.draft} set={set} />}</Card>
          <Card title={<span className="flex items-center gap-2"><Network size={15} /> Network access</span>}>
            {srv.draft && (
              <>
                <FieldList fields={[{ key: "host", label: "Listen on", type: "select", options: [{ value: "127.0.0.1", label: "This Mac only (most private)" }, { value: "0.0.0.0", label: "Local network (LAN)" }] }, { key: "session_hours", label: "Stay signed in for", type: "number", min: 1, max: 720, unit: "hours" }]} draft={srv.draft} set={srv.set} />
                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-500">Network changes apply after restarting the app. Never expose port 8090 directly to the internet.</p>
                  <button className="btn-ghost shrink-0" disabled={!srv.dirty} onClick={() => srv.save()}>Save</button>
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
      <SaveBar dirty={s.dirty} saving={s.saving} onSave={() => s.save()} onReset={s.reset} />
    </div>
  );
}

const Info = ({ k, v }: { k: string; v: any }) => <div className="rounded-lg bg-ink-850 p-3"><div className="label">{k}</div><div className="mono mt-1 truncate text-xs text-slate-200">{v ?? "—"}</div></div>;
function SourceOpt({ active, onClick, title, sub }: { active: boolean; onClick: () => void; title: string; sub: string }) {
  return (
    <button onClick={onClick} className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition ${active ? "border-signal/60 bg-signal/5" : "border-ink-700 bg-ink-850 hover:border-ink-500"}`}>
      <span className={`h-3.5 w-3.5 rounded-full border-2 ${active ? "border-signal bg-signal" : "border-slate-500"}`} />
      <div><div className="text-sm text-slate-100">{title}</div><div className="text-xs text-slate-500">{sub}</div></div>
    </button>
  );
}
