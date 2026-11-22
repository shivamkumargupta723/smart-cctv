import { useEffect, useState } from "react";
import {
  Video, ScanEye, History, Images, Film, Bell, Camera, Cpu, HardDrive, ScrollText, LogOut, Menu, X, ShieldCheck, Pause, Circle, Wifi, WifiOff,
} from "lucide-react";
import { get, post, setUnauthorizedHandler, fmtBytes } from "./api";
import { LiveProvider, useLive } from "./live";
import { FlashProvider, Spinner } from "./components/ui";
import LivePage from "./pages/LivePage";
import DetectionPage from "./pages/DetectionPage";
import EventsPage from "./pages/EventsPage";
import GalleryPage from "./pages/GalleryPage";
import RecordingsPage from "./pages/RecordingsPage";
import NotificationsPage from "./pages/NotificationsPage";
import CameraPage from "./pages/CameraPage";
import ModelPage from "./pages/ModelPage";
import StoragePage from "./pages/StoragePage";
import LogsPage from "./pages/LogsPage";
import Login from "./pages/Login";

const NAV = [
  { id: "live", label: "Live Camera", icon: Video, el: LivePage },
  { id: "detection", label: "AI Detection", icon: ScanEye, el: DetectionPage },
  { id: "events", label: "Event History", icon: History, el: EventsPage },
  { id: "gallery", label: "Photo Gallery", icon: Images, el: GalleryPage },
  { id: "recordings", label: "Video Recordings", icon: Film, el: RecordingsPage },
  { id: "notifications", label: "Notifications", icon: Bell, el: NotificationsPage },
  { id: "camera", label: "Camera Settings", icon: Camera, el: CameraPage },
  { id: "model", label: "AI Model Settings", icon: Cpu, el: ModelPage },
  { id: "storage", label: "Storage", icon: HardDrive, el: StoragePage },
  { id: "logs", label: "System Logs", icon: ScrollText, el: LogsPage },
];

const routeFromHash = () => {
  const h = location.hash.replace(/^#\/?/, "").split("?")[0];
  return NAV.some((n) => n.id === h) ? h : "live";
};

export default function App() {
  const [auth, setAuth] = useState<{ loading: boolean; setup: boolean; user: any }>({ loading: true, setup: false, user: null });
  const check = () => get("/api/auth/state").then((s) => setAuth({ loading: false, setup: s.setup_required, user: s.user })).catch(() => setAuth({ loading: false, setup: false, user: null }));
  useEffect(() => {
    setUnauthorizedHandler(() => setAuth((a) => ({ ...a, user: null })));
    check();
  }, []);
  if (auth.loading) return <div className="flex h-full items-center justify-center text-slate-500"><Spinner size={24} /></div>;
  return (
    <FlashProvider>
      {!auth.user ? <Login setup={auth.setup} onDone={check} /> : (
        <LiveProvider><Shell user={auth.user} onLogout={async () => { await post("/api/auth/logout"); check(); }} /></LiveProvider>
      )}
    </FlashProvider>
  );
}

function Shell({ user, onLogout }: { user: any; onLogout: () => void }) {
  const [route, setRoute] = useState(routeFromHash());
  const [open, setOpen] = useState(false);
  const { status, live, connected, toasts, dismiss } = useLive();
  useEffect(() => {
    const h = () => { setRoute(routeFromHash()); setOpen(false); };
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  const Page = NAV.find((n) => n.id === route)!.el;
  const rec = status?.recording;
  const cam = status?.camera;

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-ink-700 bg-ink-900 transition-transform lg:static lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-16 items-center gap-3 border-b border-ink-700 px-5">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-ink-800 ring-1 ring-ink-600">
            <ShieldCheck size={19} className="text-signal" />
            {rec?.recording && <span className="rec-dot absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-red-500" />}
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Smart CCTV</div>
            <div className="mono text-[10px] uppercase tracking-widest text-slate-500">Local · Private</div>
          </div>
          <button className="ml-auto text-slate-400 lg:hidden" onClick={() => setOpen(false)}><X size={18} /></button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {NAV.map((n, i) => {
            const active = n.id === route;
            return (
              <a key={n.id} href={`#/${n.id}`}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${active ? "bg-signal/10 text-signal" : "text-slate-400 hover:bg-ink-800 hover:text-slate-100"}`}>
                <n.icon size={17} />
                <span className="flex-1">{n.label}</span>
                <span className="mono text-[10px] text-slate-600">{String(i + 1).padStart(2, "0")}</span>
              </a>
            );
          })}
        </nav>
        <div className="border-t border-ink-700 p-3">
          {status && (
            <div className="mb-3 space-y-1.5 rounded-lg bg-ink-850 p-3 text-xs">
              <div className="flex justify-between text-slate-400"><span>Disk free</span><span className="mono text-slate-200">{fmtBytes(status.storage.disk_free)}</span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
                <div className={`h-full ${status.storage.low ? "bg-red-500" : "bg-signal"}`} style={{ width: `${status.storage.percent_used}%` }} />
              </div>
              <div className="flex justify-between text-slate-500"><span>AI</span><span className="mono">{status.detector.model.replace(".pt", "")} · {status.detector.device}</span></div>
            </div>
          )}
          <div className="flex items-center justify-between px-1 text-sm">
            <span className="truncate text-slate-400">{user.username}</span>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1 text-slate-400 hover:bg-ink-800 hover:text-white" onClick={onLogout}><LogOut size={15} /> Logout</button>
          </div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-950/80 px-4 backdrop-blur sm:px-6">
          <button className="text-slate-300 lg:hidden" onClick={() => setOpen(true)}><Menu size={20} /></button>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Pill ok={!!cam?.connected} warn={!!cam?.paused}>{cam?.paused ? "Camera paused" : cam?.connected ? `Camera online · ${cam.fps.toFixed(0)} fps` : "Camera offline"}</Pill>
            {rec?.paused ? (
              <span className="chip bg-amber-500/15 text-amber-300"><Pause size={12} /> Privacy pause</span>
            ) : rec?.recording ? (
              <span className="chip bg-red-500/15 text-red-300"><Circle size={9} className="rec-dot fill-red-500 text-red-500" /> REC {rec.continuous_active ? "continuous" : ""}{rec.continuous_active && rec.event_active ? " + " : ""}{rec.event_active ? "event" : ""}</span>
            ) : (
              <span className="chip bg-ink-700 text-slate-400">Not recording</span>
            )}
            <span className="chip hidden bg-ink-700 text-slate-300 sm:inline-flex">Persons <b className="mono text-signal">{live?.persons ?? 0}</b></span>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            {connected ? <Wifi size={15} className="text-emerald-400" /> : <WifiOff size={15} className="text-red-400" />}
            <span className="hidden sm:inline">{connected ? "Live" : "Reconnecting…"}</span>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-[1600px]"><Page /></div>
        </main>
      </div>

      {/* Alert toasts */}
      <div className="fixed right-4 top-20 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className="card flex gap-3 border-signal/40 bg-ink-850/95 p-3 shadow-2xl backdrop-blur">
            <Bell size={18} className="mt-0.5 shrink-0 text-signal" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-white">{t.title}</div>
              <div className="text-xs text-slate-400">{t.message}</div>
            </div>
            <button className="self-start text-slate-500 hover:text-white" onClick={() => dismiss(t.id)}><X size={14} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Pill({ ok, warn, children }: { ok: boolean; warn?: boolean; children: React.ReactNode }) {
  const c = warn ? "bg-amber-500/15 text-amber-300" : ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300";
  const d = warn ? "bg-amber-400" : ok ? "bg-emerald-400" : "bg-red-400";
  return <span className={`chip ${c}`}><span className={`h-1.5 w-1.5 rounded-full ${d}`} />{children}</span>;
}
