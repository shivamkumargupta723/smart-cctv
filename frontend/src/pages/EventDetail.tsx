import { useEffect, useState } from "react";
import { Download, Trash2, Package } from "lucide-react";
import { get, post, del, fmtTime, fmtDur, fmtBytes } from "../api";
import { Modal, Badge, EVENT_TONES, Spinner, useFlash, confirmAction } from "../components/ui";

export default function EventDetail({ id, onClose, onDeleted }: { id: number | null; onClose: () => void; onDeleted?: () => void }) {
  const [ev, setEv] = useState<any>(null);
  const [sel, setSel] = useState(0);
  const [ann, setAnn] = useState(true);
  const flash = useFlash();
  useEffect(() => {
    setEv(null);
    setSel(0);
    if (id) get(`/api/events/${id}`).then(setEv).catch((e) => flash("err", e.message));
  }, [id]);

  const exportZip = async () => {
    try {
      const r = await post("/api/export", { event_ids: [id] });
      window.location.href = r.url;
    } catch (e: any) {
      flash("err", e.message);
    }
  };
  const remove = async () => {
    if (!confirmAction("Delete this event with its photos and videos?")) return;
    try {
      await del(`/api/events/${id}`);
      flash("ok", "Event deleted");
      onDeleted?.();
      onClose();
    } catch (e: any) {
      flash("err", e.message);
    }
  };
  const snap = ev?.snapshots?.[sel];
  const rec = ev?.recordings?.find((r: any) => r.status === "complete");

  return (
    <Modal open={!!id} onClose={onClose} wide title={ev ? <span className="flex items-center gap-2"><Badge tone={EVENT_TONES[ev.type]}>{ev.type}</Badge>{ev.label} <span className="mono text-xs text-slate-500">#{ev.id}</span></span> : "Loading…"}>
      {!ev ? <div className="flex justify-center py-16"><Spinner size={22} /></div> : (
        <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
          <div className="space-y-3">
            {rec ? (
              <video key={rec.id} src={`/api/recordings/${rec.id}/video`} controls className="aspect-video w-full rounded-lg bg-black" />
            ) : snap ? (
              <img src={`/api/snapshots/${snap.id}/image?annotated=${ann ? 1 : 0}`} className="aspect-video w-full rounded-lg bg-black object-contain" alt="" />
            ) : <div className="flex aspect-video items-center justify-center rounded-lg bg-ink-850 text-sm text-slate-500">No media for this event</div>}
            {ev.snapshots.length > 0 && (
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="label">Photos ({ev.snapshots.length})</span>
                  <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={ann} onChange={(e) => setAnn(e.target.checked)} className="accent-[#f5a524]" /> AI boxes</label>
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {ev.snapshots.map((s: any, i: number) => (
                    <a key={s.id} href={`/api/snapshots/${s.id}/image?annotated=${ann ? 1 : 0}`} target="_blank" rel="noreferrer"
                      onMouseEnter={() => setSel(i)} className={`h-20 w-32 shrink-0 overflow-hidden rounded-md ring-2 ${i === sel ? "ring-signal" : "ring-transparent"}`}>
                      <img src={`/api/snapshots/${s.id}/image?thumb=1&annotated=${ann ? 1 : 0}`} className="h-full w-full object-cover" alt="" />
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="space-y-4">
            <dl className="space-y-2 rounded-lg bg-ink-850 p-3 text-sm">
              <D k="Started" v={fmtTime(ev.started_at)} />
              <D k="Ended" v={ev.ended_at ? fmtTime(ev.ended_at) : "In progress"} />
              <D k="Duration" v={ev.ended_at ? fmtDur(ev.ended_at - ev.started_at) : "—"} />
              <D k="Max people" v={ev.max_persons} />
              {ev.confidence ? <D k="Confidence" v={`${(ev.confidence * 100).toFixed(0)}%`} /> : null}
              {ev.labels?.length ? <D k="Seen" v={ev.labels.join(", ")} /> : null}
            </dl>
            {ev.recordings.length > 0 && (
              <div className="space-y-1.5">
                <span className="label">Videos</span>
                {ev.recordings.map((r: any) => (
                  <div key={r.id} className="flex items-center justify-between rounded-md bg-ink-850 px-2.5 py-2 text-xs">
                    <span className="mono text-slate-300">{fmtDur(r.duration)} · {fmtBytes(r.size)}</span>
                    {r.status === "complete" ? <a className="text-signal hover:underline" href={`/api/recordings/${r.id}/video?download=1`}><Download size={14} /></a> : <Badge tone="warn">{r.status}</Badge>}
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-col gap-2">
              <button className="btn-ghost" onClick={exportZip}><Package size={15} /> Export event (ZIP)</button>
              <button className="btn-danger" onClick={remove} disabled={!ev.ended_at}><Trash2 size={15} /> Delete event</button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

const D = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="flex justify-between gap-2"><dt className="text-slate-500">{k}</dt><dd className="mono text-right text-xs leading-5 text-slate-200">{v}</dd></div>
);
