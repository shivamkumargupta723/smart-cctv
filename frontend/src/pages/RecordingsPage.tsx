import { useEffect, useState } from "react";
import { Film, Download, Trash2, Package, Play, Circle } from "lucide-react";
import { get, post, del, qs, dateToTs, fmtTime, fmtDur, fmtBytes } from "../api";
import { Card, PageHeader, Pager, Empty, Spinner, useFlash, Modal, Badge, Toggle, confirmAction } from "../components/ui";
import { useLive } from "../live";

export default function RecordingsPage() {
  const [kind, setKind] = useState<"event" | "continuous">("event");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [play, setPlay] = useState<any>(null);
  const flash = useFlash();
  const { status, refresh } = useLive();
  const rec = status?.recording;
  const limit = 40;

  const load = () => get(`/api/recordings?${qs({ kind, start: dateToTs(from), end: dateToTs(to, true), limit, offset })}`).then(setData).catch((e) => flash("err", e.message));
  useEffect(() => { load(); }, [kind, from, to, offset]);
  useEffect(() => { const t = setInterval(load, 15000); return () => clearInterval(t); }, [kind, from, to, offset]);

  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const control = async (body: any) => {
    try { await post("/api/recording/control", body); refresh(); flash("ok", "Recording settings updated"); } catch (e: any) { flash("err", e.message); }
  };
  const exportSel = async () => {
    try { const r = await post("/api/export", { recording_ids: [...sel] }); window.location.href = r.url; } catch (e: any) { flash("err", e.message); }
  };
  const deleteSel = async () => {
    if (!confirmAction(`Delete ${sel.size} recordings permanently?`)) return;
    const r = await post("/api/recordings/delete", { ids: [...sel] });
    flash("ok", `Deleted ${r.deleted} recordings`);
    setSel(new Set());
    load();
  };
  const deleteOne = async (id: number) => {
    if (!confirmAction("Delete this recording permanently?")) return;
    try { await del(`/api/recordings/${id}`); flash("ok", "Recording deleted"); setPlay(null); load(); } catch (e: any) { flash("err", e.message); }
  };

  return (
    <div>
      <PageHeader title="Video Recordings" subtitle="H.264 MP4 files stored locally — play, download or export"
        actions={<>
          <div className="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-850 px-3 py-1.5 text-sm">Continuous <Toggle checked={!!rec?.continuous_enabled} disabled={rec?.paused} onChange={(v) => control({ continuous_enabled: v })} /></div>
          <div className="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-850 px-3 py-1.5 text-sm">Event <Toggle checked={!!rec?.event_enabled} disabled={rec?.paused} onChange={(v) => control({ event_enabled: v })} /></div>
        </>} />

      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <div className="flex rounded-lg bg-ink-850 p-1">
            {(["event", "continuous"] as const).map((k) => (
              <button key={k} onClick={() => { setKind(k); setOffset(0); setSel(new Set()); }}
                className={`rounded-md px-3 py-1.5 text-sm capitalize ${kind === k ? "bg-ink-700 text-white" : "text-slate-400 hover:text-white"}`}>{k === "event" ? "Event clips" : "Continuous 24/7"}</button>
            ))}
          </div>
          <input type="date" className="input w-40" value={from} onChange={(e) => { setFrom(e.target.value); setOffset(0); }} />
          <span className="text-xs text-slate-500">to</span>
          <input type="date" className="input w-40" value={to} onChange={(e) => { setTo(e.target.value); setOffset(0); }} />
          <div className="ml-auto flex gap-2">
            <button className="btn-ghost" disabled={!sel.size} onClick={exportSel}><Package size={15} /> Export {sel.size || ""}</button>
            <button className="btn-danger" disabled={!sel.size} onClick={deleteSel}><Trash2 size={15} /> Delete {sel.size || ""}</button>
          </div>
        </div>
        <div className="p-3">
          {!data ? <div className="flex justify-center py-16"><Spinner /></div> : !data.items.length ? (
            <Empty icon={<Film size={32} />} title={`No ${kind} recordings`} hint={kind === "continuous" ? "Enable continuous recording to keep 24/7 footage." : "Event clips are created automatically when people are detected."} />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
              {data.items.map((r) => (
                <div key={r.id} className={`overflow-hidden rounded-lg bg-ink-850 ring-2 ${sel.has(r.id) ? "ring-signal" : "ring-transparent"}`}>
                  <button className="group relative block aspect-video w-full bg-black" disabled={r.status !== "complete"} onClick={() => setPlay(r)}>
                    <img src={`/api/recordings/${r.id}/thumb`} className="h-full w-full object-cover opacity-90 group-hover:opacity-100" loading="lazy" alt="" onError={(e) => (e.currentTarget.style.display = "none")} />
                    {r.status === "complete" && <span className="absolute inset-0 flex items-center justify-center opacity-0 transition group-hover:opacity-100"><span className="rounded-full bg-black/70 p-3"><Play size={22} className="fill-white" /></span></span>}
                    {r.status === "recording" && <span className="chip absolute left-2 top-2 bg-red-600 text-white"><Circle size={8} className="rec-dot fill-white" /> Recording</span>}
                    {r.status === "complete" && <span className="mono absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-[11px]">{fmtDur(r.duration)}</span>}
                  </button>
                  <div className="flex items-center gap-2 px-3 py-2">
                    <input type="checkbox" className="accent-[#f5a524]" checked={sel.has(r.id)} disabled={r.status === "recording"} onChange={() => toggle(r.id)} />
                    <div className="min-w-0 flex-1">
                      <div className="mono truncate text-xs text-slate-300">{fmtTime(r.started_at)}</div>
                      <div className="text-[11px] text-slate-500">{fmtBytes(r.size)} {r.status === "failed" && <Badge tone="bad">failed</Badge>}</div>
                    </div>
                    {r.status === "complete" && <a className="rounded p-1 text-slate-400 hover:bg-ink-700 hover:text-white" href={`/api/recordings/${r.id}/video?download=1`} title="Download"><Download size={15} /></a>}
                    {r.status !== "recording" && <button className="rounded p-1 text-slate-400 hover:bg-red-500/20 hover:text-red-300" onClick={() => deleteOne(r.id)} title="Delete"><Trash2 size={15} /></button>}
                  </div>
                </div>
              ))}
            </div>
          )}
          <Pager total={data?.total || 0} limit={limit} offset={offset} onChange={setOffset} />
        </div>
      </Card>

      <Modal open={!!play} onClose={() => setPlay(null)} wide title={play ? <span className="mono text-xs">{play.filename} · {fmtDur(play.duration)} · {fmtBytes(play.size)}</span> : ""}>
        {play && (
          <div>
            <video src={`/api/recordings/${play.id}/video`} controls autoPlay className="max-h-[72vh] w-full rounded-lg bg-black" />
            <div className="mt-3 flex justify-end gap-2">
              <a className="btn-ghost" href={`/api/recordings/${play.id}/video?download=1`}><Download size={15} /> Download MP4</a>
              <button className="btn-danger" onClick={() => deleteOne(play.id)}><Trash2 size={15} /> Delete</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
