import { useEffect, useState } from "react";
import { Search, Trash2, Package, History, RefreshCw } from "lucide-react";
import { get, post, qs, dateToTs, fmtTime, fmtDur } from "../api";
import { Card, PageHeader, Badge, EVENT_TONES, Pager, Empty, Spinner, useFlash, confirmAction } from "../components/ui";
import { useLive } from "../live";
import EventDetail from "./EventDetail";

const TYPES = ["person", "entry", "exit", "loitering", "motion", "vehicle", "animal", "object", "camera", "storage", "manual"];

export default function EventsPage() {
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<number | null>(null);
  const flash = useFlash();
  const { events } = useLive();
  const limit = 50;

  const load = () => {
    get(`/api/events?${qs({ type, q, start: dateToTs(from), end: dateToTs(to, true), limit, offset })}`).then(setData).catch((e) => flash("err", e.message));
    get("/api/events/stats").then(setStats).catch(() => {});
  };
  useEffect(load, [type, from, to, offset]);
  useEffect(() => { const t = setTimeout(() => { setOffset(0); load(); }, 350); return () => clearTimeout(t); }, [q]);
  useEffect(() => { if (offset === 0 && !q && !from && !to) load(); }, [events[0]?.id]);

  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSel = !!data?.items.length && data.items.every((e) => selected.has(e.id));
  const bulkDelete = async () => {
    if (!confirmAction(`Delete ${selected.size} events with their photos and videos?`)) return;
    const r = await post("/api/events/delete", { ids: [...selected] });
    flash("ok", `Deleted ${r.deleted} events`);
    setSelected(new Set());
    load();
  };
  const bulkExport = async () => {
    try {
      const r = await post("/api/export", { event_ids: [...selected] });
      window.location.href = r.url;
    } catch (e: any) { flash("err", e.message); }
  };
  const maxH = Math.max(1, ...(stats?.hourly || []).map((h: any) => h.person + h.motion + h.other));

  return (
    <div>
      <PageHeader title="Event History" subtitle="Searchable timeline of everything the AI has seen"
        actions={<button className="btn-ghost" onClick={load}><RefreshCw size={15} /> Refresh</button>} />

      <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Card title="Today">
          <div className="grid grid-cols-4 gap-2">
            {["person", "entry", "motion", "vehicle", "animal", "object", "loitering", "camera"].map((t) => (
              <button key={t} onClick={() => { setType(type === t ? "" : t); setOffset(0); }}
                className={`rounded-lg px-2 py-2 text-center transition ${type === t ? "bg-signal/15 ring-1 ring-signal/50" : "bg-ink-850 hover:bg-ink-800"}`}>
                <div className="mono text-lg font-semibold text-white">{stats?.today?.[t] || 0}</div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t}</div>
              </button>
            ))}
          </div>
        </Card>
        <Card title="Activity — last 24 hours" actions={<div className="flex gap-3 text-[11px] text-slate-400"><L c="bg-signal" t="person" /><L c="bg-sky-400" t="motion" /><L c="bg-slate-400" t="other" /></div>}>
          <div className="flex h-28 items-end gap-[3px]">
            {(stats?.hourly || []).map((h: any, i: number) => {
              const hr = new Date((stats.hourly_start + i * 3600) * 1000).getHours();
              return (
                <div key={i} className="group relative flex h-full flex-1 flex-col justify-end" title={`${hr}:00 — person ${h.person}, motion ${h.motion}, other ${h.other}`}>
                  <div className="bg-slate-400/70" style={{ height: `${(h.other / maxH) * 100}%` }} />
                  <div className="bg-sky-400/80" style={{ height: `${(h.motion / maxH) * 100}%` }} />
                  <div className="rounded-t-sm bg-signal" style={{ height: `${(h.person / maxH) * 100}%` }} />
                  {i % 4 === 0 && <span className="mono absolute -bottom-4 left-0 text-[9px] text-slate-600">{String(hr).padStart(2, "0")}</span>}
                </div>
              );
            })}
          </div>
          <div className="h-3" />
        </Card>
      </div>

      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <div className="relative min-w-[200px] flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input className="input pl-9" placeholder="Search events (e.g. person, car, dog)…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-40" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}>
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="date" className="input w-40" value={from} onChange={(e) => { setFrom(e.target.value); setOffset(0); }} />
          <span className="text-xs text-slate-500">to</span>
          <input type="date" className="input w-40" value={to} onChange={(e) => { setTo(e.target.value); setOffset(0); }} />
          {selected.size > 0 && (
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={bulkExport}><Package size={15} /> Export {selected.size}</button>
              <button className="btn-danger" onClick={bulkDelete}><Trash2 size={15} /> Delete {selected.size}</button>
            </div>
          )}
        </div>
        {!data ? <div className="flex justify-center py-16"><Spinner /></div> : !data.items.length ? (
          <Empty icon={<History size={32} />} title="No events found" hint="Try clearing filters, or wait for activity in front of the camera." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-700 text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="w-10 px-3 py-2"><input type="checkbox" className="accent-[#f5a524]" checked={allSel} onChange={() => setSelected(allSel ? new Set() : new Set(data.items.map((e) => e.id)))} /></th>
                  <th className="px-2 py-2">Photo</th><th className="px-2 py-2">Type</th><th className="px-2 py-2">Description</th>
                  <th className="px-2 py-2">Time</th><th className="px-2 py-2">Duration</th><th className="px-2 py-2">People</th><th className="px-2 py-2">Media</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id} className="cursor-pointer border-b border-ink-800 hover:bg-ink-850" onClick={() => setOpen(e.id)}>
                    <td className="px-3 py-2" onClick={(x) => x.stopPropagation()}><input type="checkbox" className="accent-[#f5a524]" checked={selected.has(e.id)} onChange={() => toggle(e.id)} /></td>
                    <td className="px-2 py-2"><div className="h-10 w-16 overflow-hidden rounded bg-ink-800">{e.snapshot_id && <img src={`/api/snapshots/${e.snapshot_id}/image?thumb=1`} className="h-full w-full object-cover" loading="lazy" alt="" />}</div></td>
                    <td className="px-2 py-2"><Badge tone={EVENT_TONES[e.type]}>{e.type}</Badge></td>
                    <td className="px-2 py-2 text-slate-200">{e.label}</td>
                    <td className="mono whitespace-nowrap px-2 py-2 text-xs text-slate-400">{fmtTime(e.started_at)}</td>
                    <td className="mono px-2 py-2 text-xs text-slate-400">{e.ended_at ? (e.ended_at - e.started_at > 1 ? fmtDur(e.ended_at - e.started_at) : "—") : <Badge tone="bad">live</Badge>}</td>
                    <td className="mono px-2 py-2 text-xs">{e.max_persons || "—"}</td>
                    <td className="px-2 py-2 text-xs text-slate-400">{e.snapshot_count ? `${e.snapshot_count} 📷` : ""} {e.recording_id ? "🎞" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-3 pb-3"><Pager total={data?.total || 0} limit={limit} offset={offset} onChange={setOffset} /></div>
      </Card>
      <EventDetail id={open} onClose={() => setOpen(null)} onDeleted={load} />
    </div>
  );
}

const L = ({ c, t }: { c: string; t: string }) => <span className="flex items-center gap-1"><span className={`h-2 w-2 rounded-sm ${c}`} />{t}</span>;
