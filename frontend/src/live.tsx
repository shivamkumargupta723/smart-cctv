import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { get } from "./api";

export type Det = { label: string; category: string; confidence: number; box: number[]; track_id: number | null };
export type EventRow = {
  id: number; type: string; label: string; started_at: number; ended_at: number | null; max_persons: number;
  confidence: number | null; labels: string[] | null; snapshot_id: number | null; recording_id: number | null;
  snapshot_count?: number; recording_status?: string; details?: any;
};
export type Live = {
  persons: number; night: boolean; brightness: number; motion: boolean; inference_ms: number;
  processing_fps: number; active_event: number | null; detections: Det[];
};
export type Status = {
  ts: number; uptime: number;
  camera: { connected: boolean; source: string; index: number | null; fps: number; width: number; height: number; error: string; paused: boolean };
  recording: { paused: boolean; continuous_enabled: boolean; event_enabled: boolean; continuous_active: boolean; event_active: boolean; recording: boolean; continuous_file: string | null; event_file: string | null };
  detector: { model: string; device: string; loaded: boolean; error: string; face_detector: string; classes: string[] };
  engine: { persons: number; processing_fps: number; inference_ms: number; stream_fps: number; active_event: number | null; night: boolean };
  storage: { disk_total: number; disk_free: number; disk_used: number; percent_used: number; cctv_total: number; low: boolean };
  notifications: Record<string, { enabled: boolean; configured: boolean }>;
  cpu_percent: number; mem_percent: number;
};
export type Toast = { id: number; title: string; message: string; ts: number };

type Ctx = {
  status: Status | null; live: Live | null; events: EventRow[]; connected: boolean;
  toasts: Toast[]; dismiss: (id: number) => void; refresh: () => void;
};
const LiveCtx = createContext<Ctx>(null as any);
export const useLive = () => useContext(LiveCtx);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [connected, setConnected] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = () =>
    get("/api/status").then((s) => {
      setStatus(s);
      setLive(s.live);
      setEvents(s.recent_events || []);
    }).catch(() => {});

  useEffect(() => {
    refresh();
    let alive = true;
    let retry: number | undefined;
    let ping: number | undefined;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        ping = window.setInterval(() => ws.readyState === 1 && ws.send("ping"), 20000);
      };
      ws.onclose = () => {
        setConnected(false);
        clearInterval(ping);
        if (alive) retry = window.setTimeout(connect, 2000);
      };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.type === "status") setStatus(msg.data);
        else if (msg.type === "detections") setLive(msg.data);
        else if (msg.type === "event")
          setEvents((prev) => [msg.data, ...prev.filter((e) => e.id !== msg.data.id)].slice(0, 30));
        else if (msg.type === "notification") {
          const t: Toast = { id: Date.now() + Math.random(), title: msg.data.title, message: msg.data.message, ts: msg.data.ts };
          setToasts((p) => [t, ...p].slice(0, 4));
          setTimeout(() => setToasts((p) => p.filter((x) => x.id !== t.id)), 8000);
          if ("Notification" in window && Notification.permission === "granted") {
            try {
              const n = new Notification(t.title, { body: t.message, icon: "/favicon.svg", tag: msg.data.trigger });
              n.onclick = () => { window.focus(); n.close(); };
            } catch { /* ignore */ }
          }
        }
      };
    };
    connect();
    return () => {
      alive = false;
      clearTimeout(retry);
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, []);

  return (
    <LiveCtx.Provider value={{ status, live, events, connected, toasts, refresh, dismiss: (id) => setToasts((p) => p.filter((x) => x.id !== id)) }}>
      {children}
    </LiveCtx.Provider>
  );
}
