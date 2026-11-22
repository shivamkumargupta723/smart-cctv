import { useEffect, useState } from "react";
import { Cpu, CheckCircle2, Download, Sparkles } from "lucide-react";
import { get } from "../api";
import { Card, PageHeader, FieldList, SaveBar, useSection, Badge, type Field } from "../components/ui";
import { useLive } from "../live";

const PERF: Field[] = [
  { key: "device", label: "Compute device", type: "select", options: [
    { value: "auto", label: "Auto (Apple GPU if available)" }, { value: "mps", label: "Apple Silicon GPU (MPS)" }, { value: "cpu", label: "CPU" }, { value: "cuda", label: "NVIDIA CUDA" }] },
  { key: "imgsz", label: "Inference resolution", type: "select", options: [{ value: 320, label: "320 px — fastest" }, { value: 480, label: "480 px" }, { value: 640, label: "640 px — default" }, { value: 960, label: "960 px — small/distant people" }] },
  { key: "inference_fps", label: "Max AI frames per second", type: "number", min: 1, max: 30, unit: "fps", help: "Lower this if CPU usage is high" },
];
const CONF: Field[] = [
  { key: "person_confidence", label: "Person confidence threshold", type: "range", min: 0.2, max: 0.95, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, help: "Higher = fewer false person alerts" },
  { key: "object_confidence", label: "Object confidence threshold", type: "range", min: 0.2, max: 0.95, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%` },
];
const NIGHT: Field[] = [
  { key: "night_mode", label: "Day / night mode", type: "select", options: [{ value: "auto", label: "Automatic (by brightness)" }, { value: "day", label: "Always day" }, { value: "night", label: "Always night" }] },
  { key: "night_brightness_threshold", label: "Night below brightness", type: "range", min: 10, max: 150, help: "Average frame brightness (0-255) that switches to night settings" },
  { key: "night_person_confidence", label: "Night person confidence", type: "range", min: 0.15, max: 0.9, step: 0.01, fmt: (v) => `${Math.round(v * 100)}%`, help: "Usually lower at night because images are noisier" },
  { key: "night_enhance", label: "Low-light enhancement (CLAHE)", type: "toggle", help: "Boosts contrast before AI inference in the dark" },
];

export default function ModelPage() {
  const s = useSection<any>("detection");
  const [info, setInfo] = useState<any>(null);
  const { status, live } = useLive();
  useEffect(() => { get("/api/models").then(setInfo); }, [status?.detector.model]);
  const hw = info?.hardware;

  return (
    <div>
      <PageHeader title="AI Model Settings" subtitle="YOLO object detection, tuned for this computer" />
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="space-y-5">
          <Card title="Hardware">
            {hw && (
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[["OS", hw.os], ["Processor", hw.chip], ["CPU cores", hw.cpu_cores], ["Memory", `${hw.ram_gb} GB`], ["Accelerator", hw.accelerator], ["Python", hw.python]].map(([k, v]) => (
                  <div key={k as string} className="rounded-lg bg-ink-850 p-3"><div className="label">{k}</div><div className="mono mt-1 truncate text-xs text-slate-200">{v}</div></div>
                ))}
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={status?.detector.loaded ? "good" : "bad"}>{status?.detector.loaded ? "Model loaded" : "Model not loaded"}</Badge>
              <span className="mono text-xs text-slate-400">{status?.detector.model} on {status?.detector.device} · {live?.inference_ms?.toFixed(0)} ms/frame · faces: {status?.detector.face_detector || "off"}</span>
            </div>
            {status?.detector.error && <div className="mt-2 rounded-md bg-red-500/10 p-2 text-xs text-red-300">{status.detector.error}</div>}
          </Card>
          <Card title="Model">
            <div className="space-y-2">
              {(info?.models || []).map((m: any) => {
                const active = s.draft?.model === m.file;
                return (
                  <button key={m.file} onClick={() => s.set("model", m.file)} className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition ${active ? "border-signal/60 bg-signal/5" : "border-ink-700 bg-ink-850 hover:border-ink-500"}`}>
                    <Cpu size={18} className={active ? "text-signal" : "text-slate-500"} />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 text-sm font-medium text-white">{m.name}
                        {info.recommended === m.file && <Badge tone="signal"><Sparkles size={11} /> recommended</Badge>}
                      </div>
                      <div className="text-xs text-slate-500">{m.note} · {m.size_mb} MB</div>
                    </div>
                    {m.downloaded ? <CheckCircle2 size={16} className="text-emerald-400" /> : <span className="flex items-center gap-1 text-[11px] text-slate-500"><Download size={13} /> auto-download</span>}
                  </button>
                );
              })}
            </div>
            <p className="mt-3 text-xs text-slate-500">Changing the model reloads it in the background (downloads once if needed). Detection continues with the old model until the new one is ready.</p>
          </Card>
        </div>
        <div className="space-y-5">
          <Card title="Performance">{s.draft && <FieldList fields={PERF} draft={s.draft} set={s.set} />}</Card>
          <Card title="Confidence thresholds">{s.draft && <FieldList fields={CONF} draft={s.draft} set={s.set} />}</Card>
          <Card title="Day & night">{s.draft && <FieldList fields={NIGHT} draft={s.draft} set={s.set} />}
            <div className="mt-2 text-xs text-slate-500">Current: <span className="text-slate-300">{live?.night ? "Night" : "Day"}</span> · brightness <span className="mono">{live?.brightness}</span></div>
          </Card>
        </div>
      </div>
      <SaveBar dirty={s.dirty} saving={s.saving} onSave={() => s.save({ ...s.draft, zones: undefined })} onReset={s.reset} />
    </div>
  );
}
