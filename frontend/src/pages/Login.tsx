import { useState } from "react";
import { ShieldCheck, LogIn, UserPlus } from "lucide-react";
import { post } from "../api";
import { Spinner } from "../components/ui";

export default function Login({ setup, onDone }: { setup: boolean; onDone: () => void }) {
  const [username, setUsername] = useState(setup ? "admin" : "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (setup && password !== confirm) return setErr("Passwords do not match");
    setBusy(true);
    try {
      await post(setup ? "/api/auth/setup" : "/api/auth/login", { username, password });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden p-4">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(245,165,36,0.10),transparent_60%)]" />
      <form onSubmit={submit} className="card relative w-full max-w-sm p-7 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-ink-800 ring-1 ring-ink-600"><ShieldCheck className="text-signal" /></div>
          <div>
            <div className="text-lg font-semibold text-white">Smart CCTV</div>
            <div className="text-xs text-slate-500">{setup ? "Create the administrator account" : "Sign in to your dashboard"}</div>
          </div>
        </div>
        <label className="label">Username</label>
        <input className="input mb-4 mt-1.5" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" required />
        <label className="label">Password</label>
        <input className="input mb-4 mt-1.5" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={setup ? "new-password" : "current-password"} required minLength={setup ? 8 : 1} />
        {setup && (
          <>
            <label className="label">Confirm password</label>
            <input className="input mb-4 mt-1.5" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required minLength={8} />
            <p className="mb-4 text-xs text-slate-500">Minimum 8 characters. Everything stays on this computer.</p>
          </>
        )}
        {err && <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</div>}
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? <Spinner /> : setup ? <UserPlus size={16} /> : <LogIn size={16} />} {setup ? "Create account" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
