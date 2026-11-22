import { useEffect, useState } from "react";
import { Images, Trash2, Package, Download, Camera, ChevronLeft, ChevronRight, CheckSquare } from "lucide-react";
import { get, post, del, qs, dateToTs, fmtTime, fmtBytes } from "../api";
import { Card, PageHeader, Pager, Empty, Spinner, useFlash, Modal, Badge, confirmAction } from "../components/ui";

export default function GalleryPage() {
  const [label, setLabel] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: any[]; labels: string[] } | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [selecting, setSelecting] = useState(false);
  const [view, setView] = useState<number | null>(null);
  const [ann, setAnn] = useState(false);
  const flash = useFlash();
  const limit = 48;

  const load = () => get(`/api/snapshots?${qs({ label, start: dateToTs(from), end: dateToTs(to, true), limit, offset })}`).then(setData).catch((e) => flash("err", e.message));
  useEffect(() => { load(); }, [label, from, to, offset]);

  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const capture = async () => {
    try { await post("/api/snapshots/capture"); flash("ok", "Snapshot captured"); setOffset(0); load(); } catch (e: any) { flash("err", e.message); }
  };
  const exportSel = async () => {
    try { const r = await post("/api/export", { snapshot_ids: [...sel] }); window.location.href = r.url; } catch (e: any) { flash("err", e.message); }
  };
  const deleteSel = async () => {
    if (!confirmAction(`Delete ${sel.size} photos permanently?`)) return;
    const r = await post("/api/snapshots/delete", { ids: [...sel] });
    flash("ok", `Deleted ${r.deleted} photos`);
    setSel(new Set());
    load();
  };
  const deleteOne = async (id: number) => {
    if (!confirmAction("Delete this photo permanently?")) return;
    await del(`/api/snapshots/${id}`);
    flash("ok", "Photo deleted");
    setView(null);
    load();
  };
  const items = data?.items || [];
  const idx = items.findIndex((s) => s.id === view);
  const cur = idx >= 0 ? items[idx] : null;

  useEffect(() => {
    if (view === null) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" && idx < items.length - 1) setView(items[idx + 1].id);
      if (e.key === "ArrowLeft" && idx > 0) setView(items[idx - 1].id);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [view, idx, items]);

  return (
    <div>
      <PageHeader title="Photo Gallery" subtitle={`${data?.total ?? 0} photos captured automatically on detection`}
        actions={<>
          <button className="btn-ghost" onClick={capture}><Camera size={15} /> Capture now</button>
          <button className={`btn-ghost ${selecting ? "!border-signal/50 text-signal" : ""}`} onClick={() => { setSelecting(!selecting); setSel(new Set()); }}><CheckSquare size={15} /> Select</button>
        </>} />
      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <select className="input w-44" value={label} onChange={(e) => { setLabel(e.target.value); setOffset(0); }}>
            <option value="">All photos</option>
            {(data?.labels || []).map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <input type="date" className="input w-40" value={from} onChange={(e) => { setFrom(e.target.value); setOffset(0); }} />
          <span className="text-xs text-slate-500">to</span>
          <input type="date" className="input w-40" value={to} onChange={(e) => { setTo(e.target.value); setOffset(0); }} />
          {selecting && (
            <div className="ml-auto flex items-center gap-2">
              <button className="btn-ghost" onClick={() => setSel(new Set(items.map((s) => s.id)))}>Select page</button>
              <button className="btn-ghost" disabled={!sel.size} onClick={exportSel}><Package size={15} /> Export {sel.size || ""}</button>
              <button className="btn-danger" disabled={!sel.size} onClick={deleteSel}><Trash2 size={15} /> Delete {sel.size || ""}</button>
            </div>
          )}
        </div>
        <div className="p-3">
          {!data ? <div className="flex justify-center py-16"><Spinner /></div> : !items.length ? (
            <Empty icon={<Images size={32} />} title="No photos yet" hint="Photos are saved automatically when a person or configured object is detected." />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
              {items.map((s) => (
                <button key={s.id} onClick={() => (selecting ? toggle(s.id) : setView(s.id))}
                  className={`group relative overflow-hidden rounded-lg bg-ink-850 text-left ring-2 transition ${sel.has(s.id) ? "ring-signal" : "ring-transparent hover:ring-ink-500"}`}>
                  <img src={`/api/snapshots/${s.id}/image?thumb=1`} loading="lazy" className="aspect-video w-full object-cover" alt="" />
                  <div className="flex items-center justify-between px-2 py-1.5">
                    <span className="mono truncate text-[11px] text-slate-400">{fmtTime(s.created_at)}</span>
                    <Badge tone={s.label === "person" ? "signal" : "default"}>{s.label}</Badge>
                  </div>
                  {selecting && <span className={`absolute left-2 top-2 h-5 w-5 rounded border-2 ${sel.has(s.id) ? "border-signal bg-signal" : "border-white/70 bg-black/40"}`} />}
                </button>
              ))}
            </div>
          )}
          <Pager total={data?.total || 0} limit={limit} offset={offset} onChange={setOffset} />
        </div>
      </Card>

      <Modal open={!!cur} onClose={() => setView(null)} wide title={cur ? <span className="mono text-xs">{fmtTime(cur.created_at)} · {cur.label} · {cur.width}×{cur.height} · {fmtBytes(cur.size)}</span> : ""}>
        {cur && (
          <div>
            <div className="relative">
              <img src={`/api/snapshots/${cur.id}/image?annotated=${ann && cur.has_annotated ? 1 : 0}`} className="max-h-[72vh] w-full rounded-lg bg-black object-contain" alt="" />
              {idx > 0 && <button className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/60 p-2 hover:bg-black" onClick={() => setView(items[idx - 1].id)}><ChevronLeft /></button>}
              {idx < items.length - 1 && <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/60 p-2 hover:bg-black" onClick={() => setView(items[idx + 1].id)}><ChevronRight /></button>}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {!!cur.has_annotated && <label className="mr-auto flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" className="accent-[#f5a524]" checked={ann} onChange={(e) => setAnn(e.target.checked)} /> Show AI detection boxes</label>}
              <a className="btn-ghost" href={`/api/snapshots/${cur.id}/image?download=1&annotated=${ann && cur.has_annotated ? 1 : 0}`}><Download size={15} /> Download</a>
              <button className="btn-danger" onClick={() => deleteOne(cur.id)}><Trash2 size={15} /> Delete</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
