import { useEffect, useRef, useState } from "react";
import { Download, Pause, Play, Trash } from "lucide-react";
import { get, qs } from "../api";
import { Card, PageHeader, Toggle } from "../components/ui";

type Log = { id: number; ts: number; level: string; logger: string; message: string };
const LEVEL_C: Record<string, string> = { DEBUG: "text-slate-500", INFO: "text-sky-300", WARNING: "text-amber-300", ERROR: "text-red-400", CRITICAL: "text-red-500" };

export default function LogsPage() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");
  const [live, setLive] = useState(true);
  const [follow, setFollow] = useState(true);
  const lastId = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  const load = async (reset = false) => {
    if (reset) lastId.current = 0;
    const r = await get(`/api/logs?${qs({ level, search, since: lastId.current, limit: 1500 })}`);
    if (r.items.length) lastId.current = r.items[r.items.length - 1].id;
    setLogs((p) => (reset ? r.items : [...p, ...r.items]).slice(-3000));
  };
  useEffect(() => { const t = setTimeout(() => load(true), 250); return () => clearTimeout(t); }, [level, search]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => load(), 2000);
    return () => clearInterval(t);
  }, [live, level, search]);
  useEffect(() => { if (follow && box.current) box.current.scrollTop = box.current.scrollHeight; }, [logs, follow]);

  return (
    <div>
      <PageHeader title="System Logs" subtitle="Camera, AI, recording and notification activity"
        actions={<>
          <button className="btn-ghost" onClick={() => setLive(!live)}>{live ? <Pause size={15} /> : <Play size={15} />} {live ? "Pause" : "Resume"}</button>
          <button className="btn-ghost" onClick={() => setLogs([])}><Trash size={15} /> Clear view</button>
          <a className="btn-ghost" href="/api/logs/download"><Download size={15} /> Download log file</a>
        </>} />
      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <select className="input w-40" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">All levels</option><option value="INFO">Info +</option><option value="WARNING">Warnings +</option><option value="ERROR">Errors only</option>
          </select>
          <input className="input max-w-xs" placeholder="Filter text…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <label className="ml-auto flex items-center gap-2 text-xs text-slate-400">Auto-scroll <Toggle checked={follow} onChange={setFollow} /></label>
        </div>
        <div ref={box} className="mono h-[68vh] overflow-y-auto bg-ink-950 p-3 text-[12px] leading-relaxed">
          {logs.map((l) => (
            <div key={l.id} className="flex gap-3 whitespace-pre-wrap break-all hover:bg-ink-900">
              <span className="shrink-0 text-slate-600">{new Date(l.ts * 1000).toLocaleString()}</span>
              <span className={`w-16 shrink-0 ${LEVEL_C[l.level] || ""}`}>{l.level}</span>
              <span className="w-20 shrink-0 truncate text-slate-500">{l.logger}</span>
              <span className="text-slate-300">{l.message}</span>
            </div>
          ))}
          {!logs.length && <div className="py-10 text-center text-slate-600">No log entries</div>}
        </div>
      </Card>
    </div>
  );
}
