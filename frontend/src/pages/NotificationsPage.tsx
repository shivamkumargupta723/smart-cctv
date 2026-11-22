import { useEffect, useState } from "react";
import { Send, BellRing, MessageCircle, Smartphone, Mail, Globe, RefreshCw } from "lucide-react";
import { get, post, fmtTime } from "../api";
import { Card, PageHeader, FieldList, SaveBar, useSection, useFlash, Toggle, Badge, Spinner, type Field } from "../components/ui";

const TRIGGERS: Field[] = [
  { key: "triggers.person_entered", label: "Person enters the camera view", type: "toggle" },
  { key: "triggers.person_loitering", label: "Person remains in the monitored area", type: "toggle" },
  { key: "triggers.motion", label: "Motion detected (no person)", type: "toggle" },
  { key: "triggers.object", label: "Configured object appears", type: "toggle", help: "Objects selected under AI Detection → Alert objects" },
  { key: "triggers.camera_disconnected", label: "Camera disconnects", type: "toggle" },
  { key: "triggers.storage_low", label: "Storage running low", type: "toggle" },
  { key: "cooldown_seconds", label: "Minimum time between repeated alerts", type: "number", min: 0, max: 86400, unit: "sec" },
];

const CHANNELS: { id: string; title: string; icon: any; desc: string; fields: Field[]; guide: string }[] = [
  { id: "browser", title: "Browser notifications", icon: Globe, desc: "Desktop pop-ups while the dashboard is open in any tab.", fields: [], guide: "" },
  {
    id: "telegram", title: "Telegram", icon: MessageCircle, desc: "Photo alerts to your Telegram chat via your own bot.",
    fields: [
      { key: "bot_token", label: "Bot token", type: "password", placeholder: "123456:ABC-DEF…" },
      { key: "chat_id", label: "Chat ID", type: "text", placeholder: "e.g. 123456789" },
    ],
    guide: "Open @BotFather in Telegram → /newbot → copy the token. Send any message to your bot, then open https://api.telegram.org/bot<TOKEN>/getUpdates and copy chat.id.",
  },
  {
    id: "ntfy", title: "Mobile push (ntfy)", icon: Smartphone, desc: "Secure push notifications to the ntfy app on iPhone/Android, with photo.",
    fields: [
      { key: "server", label: "Server URL", type: "text", placeholder: "https://ntfy.sh" },
      { key: "topic", label: "Topic", type: "text", placeholder: "long-random-private-name" },
      { key: "token", label: "Access token (optional)", type: "password", placeholder: "tk_…" },
      { key: "priority", label: "Priority", type: "select", options: [1, 2, 3, 4, 5].map((v) => ({ value: v, label: ["", "Min", "Low", "Default", "High", "Urgent"][v] })) },
    ],
    guide: "Install the ntfy app, subscribe to a long random topic name (it acts like a password), and enter the same topic here. For full privacy use an access token or a self-hosted ntfy server.",
  },
  {
    id: "whatsapp", title: "WhatsApp (Business Cloud API)", icon: MessageCircle, desc: "Official Meta WhatsApp Business Cloud API.",
    fields: [
      { key: "access_token", label: "Access token", type: "password" },
      { key: "phone_number_id", label: "Phone number ID", type: "text" },
      { key: "recipient", label: "Recipient number", type: "text", placeholder: "919876543210" },
      { key: "api_version", label: "Graph API version", type: "text", placeholder: "v21.0" },
    ],
    guide: "Create an app at developers.facebook.com → WhatsApp → API Setup. Copy the Phone number ID and a permanent System User token. Meta only delivers free-form messages within 24h after the recipient last messaged your business number — send it a message first.",
  },
  {
    id: "email", title: "Email (SMTP)", icon: Mail, desc: "Email alerts with the photo attached.",
    fields: [
      { key: "smtp_host", label: "SMTP host", type: "text", placeholder: "smtp.gmail.com" },
      { key: "smtp_port", label: "SMTP port", type: "number", min: 1, max: 65535 },
      { key: "use_tls", label: "STARTTLS", type: "toggle", help: "Port 465 always uses SSL" },
      { key: "username", label: "Username", type: "text" },
      { key: "password", label: "Password / App password", type: "password" },
      { key: "from_addr", label: "From address", type: "text" },
      { key: "to_addr", label: "Send alerts to", type: "text" },
    ],
    guide: "For Gmail turn on 2-Step Verification and create an App Password (Google Account → Security → App passwords).",
  },
];

export default function NotificationsPage() {
  const s = useSection<any>("notifications");
  const flash = useFlash();
  const [hist, setHist] = useState<any>(null);
  const [testing, setTesting] = useState("");
  const [perm, setPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const loadHist = () => get("/api/notifications?limit=60").then(setHist);
  useEffect(() => { loadHist(); }, []);

  const test = async (ch: string) => {
    if (s.dirty) await s.save();
    setTesting(ch);
    try {
      await post(`/api/notifications/test/${ch}`);
      flash("ok", `Test sent via ${ch}`);
    } catch (e: any) {
      flash("err", `${ch}: ${e.message}`);
    } finally {
      setTesting("");
      loadHist();
    }
  };
  const askPerm = async () => {
    if (typeof Notification === "undefined") return flash("err", "This browser does not support notifications");
    const p = await Notification.requestPermission();
    setPerm(p);
    if (p === "granted") new Notification("Smart CCTV", { body: "Browser notifications are enabled", icon: "/favicon.svg" });
  };

  return (
    <div>
      <PageHeader title="Notifications" subtitle="Instant alerts with photo and timestamp" actions={<button className="btn-ghost" onClick={loadHist}><RefreshCw size={15} /> Refresh</button>} />
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="space-y-5">
          <Card title="Alert triggers">{s.draft && <FieldList fields={TRIGGERS} draft={s.draft} set={s.set} />}</Card>
          <Card title="Recent notifications" pad={false}>
            <div className="max-h-[520px] overflow-y-auto">
              {!hist ? <div className="flex justify-center py-10"><Spinner /></div> : !hist.items.length ? <div className="py-10 text-center text-sm text-slate-500">No notifications sent yet</div> : (
                <table className="w-full text-sm">
                  <tbody>
                    {hist.items.map((n: any) => (
                      <tr key={n.id} className="border-b border-ink-800">
                        <td className="mono whitespace-nowrap px-4 py-2 text-xs text-slate-500">{fmtTime(n.created_at)}</td>
                        <td className="px-2 py-2"><Badge>{n.channel}</Badge></td>
                        <td className="px-2 py-2 text-slate-200">{n.title}{n.error && <div className="text-[11px] text-red-400">{n.error}</div>}</td>
                        <td className="px-4 py-2 text-right"><Badge tone={n.status === "sent" ? "good" : n.status === "failed" ? "bad" : "default"}>{n.status}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
        </div>
        <div className="space-y-5">
          {s.draft && CHANNELS.map((c) => {
            const cfg = s.draft[c.id] || {};
            return (
              <Card key={c.id} title={<span className="flex items-center gap-2"><c.icon size={15} className="text-signal" /> {c.title}</span>}
                actions={<>
                  <button className="btn-ghost py-1 text-xs" onClick={() => test(c.id)} disabled={!!testing}>{testing === c.id ? <Spinner size={13} /> : <Send size={13} />} Test</button>
                  <Toggle checked={!!cfg.enabled} onChange={(v) => s.set(`${c.id}.enabled`, v)} />
                </>}>
                <p className="text-xs text-slate-400">{c.desc}</p>
                {c.id === "browser" && (
                  <div className="mt-3 flex items-center justify-between rounded-lg bg-ink-850 p-3 text-sm">
                    <span className="flex items-center gap-2"><BellRing size={15} /> Permission: <Badge tone={perm === "granted" ? "good" : perm === "denied" ? "bad" : "warn"}>{perm}</Badge></span>
                    {perm !== "granted" && <button className="btn-primary py-1.5 text-xs" onClick={askPerm}>Allow notifications</button>}
                  </div>
                )}
                {c.fields.length > 0 && <div className="mt-2"><FieldList fields={c.fields} draft={s.draft} set={s.set} prefix={`${c.id}.`} /></div>}
                {c.guide && <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer text-slate-400 hover:text-white">Setup guide</summary><p className="mt-2 leading-relaxed">{c.guide}</p></details>}
              </Card>
            );
          })}
        </div>
      </div>
      <SaveBar dirty={s.dirty} saving={s.saving} onSave={() => s.save()} onReset={s.reset} />
    </div>
  );
}
