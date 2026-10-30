import { useEffect, useState } from "react";
import { Check, Eye, EyeOff, KeyRound, Link2, Save, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { API_BASE_URL } from "../../api/client";
import { useAuth } from "../../app/auth";
import { useHealthChecks } from "../../api/hooks";
import { Badge, Button, Card, ConfirmationDialog, Input, Label } from "../../components/ui";
import { PageHeader } from "../../components/layout";

export function SettingsPage() {
  const { token, setToken, clearToken, hasToken } = useAuth();
  const health = useHealthChecks();
  const [draftToken, setDraftToken] = useState(token);
  const [showToken, setShowToken] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  useEffect(() => setDraftToken(token), [token]);
  const save = () => {
    if (!draftToken.trim()) { toast.error("Paste a client bearer token first."); return; }
    setToken(draftToken); setSaved(true); toast.success("API client token is active in memory for this page session."); window.setTimeout(() => setSaved(false), 1800);
  };
  const clear = () => { clearToken(); setDraftToken(""); toast.success("API token removed from this tab."); };
  return <>
    <PageHeader eyebrow="Workspace configuration" title="Settings" description="Configure the API client credential for this page session." />
    <div className="grid gap-5 xl:grid-cols-[1.35fr_.65fr]"><div className="space-y-5">
      <Card className="p-5 sm:p-7"><div className="mb-6 flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-600"><Link2 size={19} /></div><div><h2 className="text-sm font-bold text-slate-900">Backend connection</h2><p className="mt-1 text-xs text-slate-500">API base URL comes from the Vite environment.</p></div></div>
        <div className="space-y-5"><div className="space-y-2"><Label htmlFor="api-url">VITE_API_BASE_URL</Label><Input id="api-url" value={API_BASE_URL} readOnly className="bg-slate-50" /><p className="text-[11px] text-slate-400">Set this in frontend/.env. Development requests use the Vite same-origin proxy to this target.</p></div>
          <div className="space-y-2"><div className="flex items-center justify-between"><Label htmlFor="client-token">API client token</Label><span className={"inline-flex items-center gap-1 text-[10px] font-semibold " + (hasToken ? "text-emerald-700" : "text-amber-700")}><span className={"h-1.5 w-1.5 rounded-full " + (hasToken ? "bg-emerald-500" : "bg-amber-500")} />{hasToken ? "Active in memory" : "Not connected"}</span></div><div className="relative"><Input id="client-token" type={showToken ? "text" : "password"} value={draftToken} onChange={(event) => setDraftToken(event.target.value)} placeholder="CLIENT_UUID.SECRET" autoComplete="off" className="pr-11" /><button type="button" aria-label={showToken ? "Hide token" : "Show token"} onClick={() => setShowToken(!showToken)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">{showToken ? <EyeOff size={16} /> : <Eye size={16} />}</button></div><p className="text-[11px] leading-relaxed text-slate-400">Paste a token created with the backend client_credentials command. It stays only in JavaScript memory and is lost on reload. Never paste an LLM provider key here.</p></div>
          <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-5">{hasToken && <Button variant="outline" onClick={() => setConfirmClear(true)}><Trash2 size={14} />Remove token</Button>}<Button onClick={save}>{saved ? <Check size={15} /> : <Save size={15} />}{saved ? "Saved" : "Save connection"}</Button></div>
        </div>
      </Card>
      <Card className="p-5 sm:p-7"><div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600"><ShieldCheck size={18} /></div><div><h2 className="text-sm font-bold text-slate-900">Credential handling</h2><p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">This backend accepts a client Bearer token, so a browser client must possess that token to call protected routes. Memory-only storage avoids persistence but does not protect it from scripts running in the page or the browser owner. Use a server-side backend-for-frontend for production user-facing deployments; never use Django, database, broker, or LLM provider credentials here.</p></div></div></Card>
      <Card className="p-5 sm:p-7"><h2 className="text-sm font-bold text-slate-900">Environment and application</h2><p className="mt-1 text-xs text-slate-500">Frontend mode and live checks returned by the backend.</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><InfoRow label="Application" value="EventFlow AI" /><InfoRow label="Frontend mode" value={import.meta.env.MODE} /><InfoRow label="API process" value={health.live.data?.status === "ok" ? "Operational" : health.live.isError ? "Unavailable" : "Checking"} /><InfoRow label="Database readiness" value={health.ready.data?.checks?.database ?? (health.ready.isError ? "unavailable" : "Checking")} /></div><p className="mt-3 text-[10px] text-slate-400">The backend does not expose client identity metadata. No token value is shown in this section.</p></Card>
    </div><Card className="h-fit bg-slate-950 p-5 text-white sm:p-6"><div className="mb-4 grid h-9 w-9 place-items-center rounded-lg bg-blue-500/15 text-blue-300"><KeyRound size={17} /></div><h2 className="text-sm font-bold">Where to get a token</h2><p className="mt-2 text-xs leading-relaxed text-slate-400">Create an API client credential in the environment where your backend is running. The secret is shown once.</p><div className="mt-4 rounded-lg border border-white/10 bg-white/[0.04] p-3 font-mono text-[10px] leading-relaxed text-slate-300">docker compose exec -T api python manage.py client_credentials create --name "local-demo"</div><a href={API_BASE_URL.replace(/\/$/, "") + "/api/docs/"} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-blue-300 hover:text-blue-200">Open API docs</a></Card></div>
    <ConfirmationDialog open={confirmClear} onOpenChange={setConfirmClear} title="Remove API token?" description="Protected API requests from this tab will stop until you enter a client token again." confirmLabel="Remove token" destructive onConfirm={clear} />
  </>;
}

function InfoRow({ label, value }: { label: string; value: string }) { const confirmed = ["Operational", "ok"].includes(value); return <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-3"><span className="text-xs text-slate-500">{label}</span><Badge variant={confirmed ? "success" : value === "unavailable" || value === "Unavailable" ? "danger" : "neutral"}>{value}</Badge></div>; }
