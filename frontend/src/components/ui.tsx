import { X, Loader2, Check, AlertTriangle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { get, put } from "../api";

export function Card({ title, actions, children, className = "", pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-4 py-3 sm:px-5">
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? "card-pad" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

export function Stat({ label, value, sub, tone = "default", icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "default" | "good" | "bad" | "warn" | "signal"; icon?: ReactNode }) {
  const tones = { default: "text-white", good: "text-emerald-400", bad: "text-red-400", warn: "text-amber-300", signal: "text-signal" };
  return (
    <div className="card card-pad">
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <span className="text-slate-500">{icon}</span>
      </div>
      <div className={`mono mt-2 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {sub && <div className="mt-1 truncate text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? "bg-signal" : "bg-ink-600"} disabled:opacity-50`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "good" | "bad" | "warn" | "info" | "signal" }) {
  const t = {
    default: "bg-ink-700 text-slate-300", good: "bg-emerald-500/15 text-emerald-300", bad: "bg-red-500/15 text-red-300",
    warn: "bg-amber-500/15 text-amber-300", info: "bg-sky-500/15 text-sky-300", signal: "bg-signal/15 text-signal",
  };
  return <span className={`chip ${t[tone]}`}>{children}</span>;
}

export const EVENT_TONES: Record<string, "default" | "good" | "bad" | "warn" | "info" | "signal"> = {
  person: "signal", entry: "good", exit: "default", loitering: "warn", motion: "info", vehicle: "info",
  animal: "good", object: "default", camera: "bad", storage: "bad", manual: "default",
};

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 backdrop-blur-sm" onClick={onClose}>
      <div className={`card max-h-[94vh] w-full overflow-auto ${wide ? "max-w-6xl" : "max-w-lg"}`} onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-ink-700 bg-ink-900 px-4 py-3">
          <div className="text-sm font-semibold text-white">{title}</div>
          <button className="rounded-md p-1 text-slate-400 hover:bg-ink-700 hover:text-white" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Empty({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <div className="mb-3 text-slate-600">{icon}</div>
      <div className="text-sm font-medium text-slate-300">{title}</div>
      {hint && <div className="mt-1 max-w-sm text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin" />;
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
      <span className="mono">{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
      <div className="flex gap-2">
        <button className="btn-ghost px-2.5 py-1" disabled={page <= 1} onClick={() => onChange(offset - limit)}>Prev</button>
        <span className="mono self-center">{page}/{pages}</span>
        <button className="btn-ghost px-2.5 py-1" disabled={page >= pages} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </div>
  );
}

// ---------------- toast feedback ----------------
type Flash = { id: number; kind: "ok" | "err"; text: string };
const FlashCtx = createContext<(kind: "ok" | "err", text: string) => void>(() => {});
export const useFlash = () => useContext(FlashCtx);
export function FlashProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Flash[]>([]);
  const push = useCallback((kind: "ok" | "err", text: string) => {
    const f = { id: Date.now() + Math.random(), kind, text };
    setItems((p) => [...p, f]);
    setTimeout(() => setItems((p) => p.filter((x) => x.id !== f.id)), 4500);
  }, []);
  return (
    <FlashCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex -translate-x-1/2 flex-col items-center gap-2">
        {items.map((f) => (
          <div key={f.id} className={`pointer-events-auto flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm shadow-xl ${f.kind === "ok" ? "border-emerald-500/30 bg-emerald-950/90 text-emerald-200" : "border-red-500/30 bg-red-950/90 text-red-200"}`}>
            {f.kind === "ok" ? <Check size={15} /> : <AlertTriangle size={15} />} {f.text}
          </div>
        ))}
      </div>
    </FlashCtx.Provider>
  );
}

// ---------------- settings form engine ----------------
export type Field =
  | { key: string; label: string; type: "toggle"; help?: string }
  | { key: string; label: string; type: "number"; min?: number; max?: number; step?: number; unit?: string; help?: string }
  | { key: string; label: string; type: "range"; min: number; max: number; step?: number; unit?: string; help?: string; fmt?: (v: number) => string }
  | { key: string; label: string; type: "text" | "password"; placeholder?: string; help?: string }
  | { key: string; label: string; type: "select"; options: { value: string | number; label: string }[]; help?: string };

export const getPath = (o: any, p: string) => p.split(".").reduce((a, k) => (a == null ? undefined : a[k]), o);
export const setPath = (o: any, p: string, v: any) => {
  const parts = p.split(".");
  const out = structuredClone(o ?? {});
  let cur = out;
  parts.slice(0, -1).forEach((k) => (cur = cur[k] = cur[k] ?? {}));
  cur[parts[parts.length - 1]] = v;
  return out;
};

export function useSection<T = any>(section: string) {
  const [data, setData] = useState<T | null>(null);
  const [draft, setDraft] = useState<T | null>(null);
  const [saving, setSaving] = useState(false);
  const flash = useFlash();
  const load = useCallback(() => get("/api/settings").then((s) => { setData(s[section]); setDraft(s[section]); }), [section]);
  useEffect(() => { load(); }, [load]);
  const dirty = JSON.stringify(data) !== JSON.stringify(draft);
  const save = async (override?: Partial<T>) => {
    setSaving(true);
    try {
      const res = await put(`/api/settings/${section}`, override ?? draft);
      setData(res);
      setDraft(res);
      flash("ok", "Settings saved");
      return res;
    } catch (e: any) {
      flash("err", e.message);
    } finally {
      setSaving(false);
    }
  };
  const set = (path: string, v: any) => setDraft((d) => setPath(d, path, v));
  return { data, draft, set, save, saving, dirty, reset: () => setDraft(data), reload: load };
}

export function FieldRow({ f, value, onChange }: { f: Field; value: any; onChange: (v: any) => void }) {
  const control = (() => {
    switch (f.type) {
      case "toggle":
        return <Toggle checked={!!value} onChange={onChange} />;
      case "number":
        return (
          <div className="flex items-center gap-2">
            <input type="number" className="input w-32 text-right mono" value={value ?? ""} min={f.min} max={f.max} step={f.step ?? 1}
              onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
            {f.unit && <span className="w-10 text-xs text-slate-500">{f.unit}</span>}
          </div>
        );
      case "range":
        return (
          <div className="flex w-full max-w-xs items-center gap-3">
            <input type="range" className="w-full accent-[#f5a524]" min={f.min} max={f.max} step={f.step ?? 1} value={value ?? f.min}
              onChange={(e) => onChange(Number(e.target.value))} />
            <span className="mono w-14 text-right text-sm text-slate-200">{f.fmt ? f.fmt(Number(value)) : value}{f.unit}</span>
          </div>
        );
      case "select":
        return (
          <select className="input w-56" value={value ?? ""} onChange={(e) => {
            const opt = f.options.find((o) => String(o.value) === e.target.value);
            onChange(opt ? opt.value : e.target.value);
          }}>
            {f.options.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
          </select>
        );
      default:
        return <input type={f.type} className="input w-full max-w-xs" value={value ?? ""} placeholder={(f as any).placeholder} autoComplete="off"
          onChange={(e) => onChange(e.target.value)} />;
    }
  })();
  return (
    <div className="flex flex-col gap-2 border-b border-ink-800 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm text-slate-200">{f.label}</div>
        {f.help && <div className="mt-0.5 text-xs text-slate-500">{f.help}</div>}
      </div>
      <div className="flex shrink-0 justify-start sm:justify-end">{control}</div>
    </div>
  );
}

export function FieldList({ fields, draft, set, prefix = "" }: { fields: Field[]; draft: any; set: (p: string, v: any) => void; prefix?: string }) {
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.key} f={f} value={getPath(draft, prefix + f.key)} onChange={(v) => set(prefix + f.key, v)} />
      ))}
    </div>
  );
}

export function SaveBar({ dirty, saving, onSave, onReset }: { dirty: boolean; saving: boolean; onSave: () => void; onReset: () => void }) {
  return (
    <div className={`sticky bottom-3 z-20 mt-5 flex items-center justify-end gap-2 rounded-xl border border-ink-600 bg-ink-850/95 p-3 shadow-2xl backdrop-blur transition ${dirty ? "opacity-100" : "pointer-events-none opacity-0"}`}>
      <span className="mr-auto text-sm text-slate-300">You have unsaved changes</span>
      <button className="btn-ghost" onClick={onReset} disabled={saving}>Discard</button>
      <button className="btn-primary" onClick={onSave} disabled={saving}>{saving ? <Spinner /> : <Check size={15} />} Save changes</button>
    </div>
  );
}

export function confirmAction(msg: string) {
  return window.confirm(msg);
}
