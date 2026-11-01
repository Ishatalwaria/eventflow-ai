import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Link2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  User,
} from "lucide-react";
import { toast } from "sonner";
import { API_BASE_URL, apiErrorMessage } from "../../api/client";
import { useAuth } from "../../app/auth";
import { useHealthChecks } from "../../api/hooks";
import { authService } from "../../api/services/auth";
import type { APIClientRecord, CreatedAPIClientRecord } from "../../api/types";
import {
  Badge,
  Button,
  Card,
  ConfirmationDialog,
  Dialog,
  DialogContent,
  Input,
  Label,
} from "../../components/ui";
import { PageHeader } from "../../components/layout";

export function SettingsPage() {
  const { user, token, setToken, clearToken, hasToken } = useAuth();
  const health = useHealthChecks();

  const [draftToken, setDraftToken] = useState(token);
  const [showToken, setShowToken] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  // API Client Management state
  const [clients, setClients] = useState<APIClientRecord[]>([]);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newClientName, setNewClientName] = useState("");
  const [newCanViewAnalytics, setNewCanViewAnalytics] = useState(false);
  const [creatingClient, setCreatingClient] = useState(false);
  const [createdSecretData, setCreatedSecretData] = useState<CreatedAPIClientRecord | null>(null);
  const [copied, setCopied] = useState(false);

  const [revokingClient, setRevokingClient] = useState<APIClientRecord | null>(null);

  useEffect(() => {
    setDraftToken(token);
  }, [token]);

  const fetchClients = async () => {
    if (!user) return;
    setClientsLoading(true);
    try {
      const data = await authService.listClients();
      setClients(data.results);
    } catch {
      // ignore
    } finally {
      setClientsLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, [user]);

  const handleCreateClient = async () => {
    if (!newClientName.trim()) {
      toast.error("Please enter a client name.");
      return;
    }
    setCreatingClient(true);
    try {
      const created = await authService.createClient({
        name: newClientName.trim(),
        can_view_analytics: newCanViewAnalytics,
      });
      setCreatedSecretData(created);
      setNewClientName("");
      setNewCanViewAnalytics(false);
      await fetchClients();
      toast.success("API client generated successfully.");
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setCreatingClient(false);
    }
  };

  const handleRevokeClient = async () => {
    if (!revokingClient) return;
    try {
      await authService.revokeClient(revokingClient.id);
      toast.success(`API client "${revokingClient.name}" has been revoked.`);
      await fetchClients();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setRevokingClient(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Copied to clipboard!");
    setTimeout(() => setCopied(false), 2000);
  };

  const saveToken = () => {
    if (!draftToken.trim()) {
      toast.error("Paste a client bearer token first.");
      return;
    }
    setToken(draftToken);
    setSaved(true);
    toast.success("API client token is active in memory for this page session.");
    setTimeout(() => setSaved(false), 1800);
  };

  const clear = () => {
    clearToken();
    setDraftToken("");
    toast.success("API token removed from this tab.");
  };

  return (
    <>
      <PageHeader
        eyebrow="Account & Workspace Configuration"
        title="Settings"
        description="Manage your account profile, self-service API client keys, and backend connections."
      />

      <div className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]">
        <div className="space-y-6">
          {/* User Profile Card */}
          <Card className="p-5 sm:p-7">
            <div className="mb-5 flex items-start gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-600">
                <User size={19} />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-900">User Profile</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Your authenticated session details.
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Name</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">
                  {user?.name || "Local Operator"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Email</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">
                  {user?.email || "N/A"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Role / Privileges</div>
                <div className="mt-1 flex items-center gap-2">
                  <Badge variant={user?.is_staff ? "warning" : "neutral"}>
                    {user?.is_staff ? "Administrator / Staff" : "Standard User"}
                  </Badge>
                </div>
              </div>
              <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Authentication Mode</div>
                <div className="mt-1 text-xs font-semibold text-emerald-600">
                  Dual-Auth HttpOnly Cookie Session
                </div>
              </div>
            </div>
          </Card>

          {/* Self-Service API Keys */}
          <Card className="p-5 sm:p-7">
            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-purple-50 text-purple-600">
                  <KeyRound size={19} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-900">API Client Keys</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Machine-to-machine credentials for automated producers and services.
                  </p>
                </div>
              </div>
              <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5 self-start sm:self-auto">
                <Plus size={15} /> Create API Key
              </Button>
            </div>

            {clientsLoading ? (
              <div className="py-8 text-center text-xs text-slate-400">Loading API keys…</div>
            ) : clients.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                No active API client keys found for your workspace. Click "Create API Key" to provision one.
              </div>
            ) : (
              <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-100">
                {clients.map((c) => (
                  <div key={c.id} className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900">{c.name}</span>
                        <Badge variant={c.is_active ? "success" : "danger"}>
                          {c.is_active ? "Active" : "Revoked"}
                        </Badge>
                        {c.can_view_analytics && (
                          <Badge variant="info">Analytics Access</Badge>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-2 font-mono text-[11px] text-slate-400">
                        <span>ID: {c.id}</span>
                        <span>•</span>
                        <span>Created: {new Date(c.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    {c.is_active && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setRevokingClient(c)}
                        className="self-end text-rose-600 hover:bg-rose-50 hover:text-rose-700 sm:self-auto"
                      >
                        <Trash2 size={14} className="mr-1" /> Revoke
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Machine Client Token Override (Optional for testing) */}
          <Card className="p-5 sm:p-7">
            <div className="mb-6 flex items-start gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-600">
                <Link2 size={19} />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-900">Backend connection</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Configure API base URL and optional client bearer token for this session.
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="api-url">API Base URL</Label>
                <Input id="api-url" value={API_BASE_URL} readOnly className="bg-slate-50" />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="client-token">Machine Bearer Token</Label>
                  <span
                    className={
                      "inline-flex items-center gap-1 text-[10px] font-semibold " +
                      (hasToken ? "text-emerald-700" : "text-slate-500")
                    }
                  >
                    <span
                      className={
                        "h-1.5 w-1.5 rounded-full " +
                        (hasToken ? "bg-emerald-500" : "bg-slate-400")
                      }
                    />
                    {hasToken ? "Overriding in memory" : "Using session cookie"}
                  </span>
                </div>
                <div className="relative">
                  <Input
                    id="client-token"
                    type={showToken ? "text" : "password"}
                    value={draftToken}
                    onChange={(event) => setDraftToken(event.target.value)}
                    placeholder="CLIENT_UUID.SECRET"
                    autoComplete="off"
                    className="pr-11"
                  />
                  <button
                    type="button"
                    aria-label={showToken ? "Hide token" : "Show token"}
                    onClick={() => setShowToken(!showToken)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  >
                    {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
                {hasToken && (
                  <Button variant="outline" onClick={() => setConfirmClear(true)}>
                    <Trash2 size={14} /> Remove token
                  </Button>
                )}
                <Button onClick={saveToken}>
                  {saved ? <Check size={15} /> : <Save size={15} />}
                  {saved ? "Saved" : "Save token"}
                </Button>
              </div>
            </div>
          </Card>

          {/* System Health Overview */}
          <Card className="p-5 sm:p-7">
            <h2 className="text-sm font-bold text-slate-900">Environment and application</h2>
            <p className="mt-1 text-xs text-slate-500">Live health checks returned by the backend.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <InfoRow label="Application" value="EventFlow AI" />
              <InfoRow label="Frontend mode" value={import.meta.env.MODE} />
              <InfoRow
                label="API process"
                value={
                  health.live.data?.status === "ok"
                    ? "Operational"
                    : health.live.isError
                    ? "Unavailable"
                    : "Checking"
                }
              />
              <InfoRow
                label="Database readiness"
                value={
                  health.ready.data?.checks?.database ??
                  (health.ready.isError ? "unavailable" : "Checking")
                }
              />
            </div>
          </Card>
        </div>

        {/* Sidebar Info */}
        <div className="space-y-6">
          <Card className="bg-slate-950 p-5 text-white sm:p-6">
            <div className="mb-4 grid h-9 w-9 place-items-center rounded-lg bg-blue-500/15 text-blue-300">
              <ShieldCheck size={17} />
            </div>
            <h2 className="text-sm font-bold">Dual-Authentication Security</h2>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              EventFlow AI uses a separated dual-tier authentication architecture:
            </p>
            <ul className="mt-3 space-y-2 text-xs text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-blue-400 font-bold">•</span>
                <span>
                  <strong>Browser Console:</strong> Authenticated via secure, HttpOnly, SameSite session cookies.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-400 font-bold">•</span>
                <span>
                  <strong>Machine API Clients:</strong> Authenticated via Bearer tokens in headers.
                </span>
              </li>
            </ul>
            <div className="mt-4 border-t border-white/10 pt-4 text-[11px] text-slate-400">
              API secrets are hashed with PBKDF2-SHA256 and never stored in plain text.
            </div>
          </Card>
        </div>
      </div>

      {/* Create Key Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Create New API Client</h2>
              <p className="mt-1 text-xs text-slate-500">
                Provision a new machine token for automated event submission.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-name">Client Name</Label>
              <Input
                id="client-name"
                placeholder="e.g. billing-service-prod"
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="analytics-perm"
                checked={newCanViewAnalytics}
                onChange={(e) => setNewCanViewAnalytics(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600"
              />
              <Label htmlFor="analytics-perm" className="text-xs font-normal text-slate-700">
                Allow ClickHouse Lifecycle Analytics queries
              </Label>
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateClient} disabled={creatingClient}>
                {creatingClient ? "Generating…" : "Generate Key"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Secret Display Dialog */}
      <Dialog
        open={Boolean(createdSecretData)}
        onOpenChange={(open) => !open && setCreatedSecretData(null)}
      >
        <DialogContent className="max-w-lg">
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900">Save Your Secret Key</h2>
                <p className="mt-1 text-xs text-slate-500">
                  This bearer token will <strong>never be shown again</strong>. Store it securely in your environment variables or secret manager.
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-slate-500">API Bearer Token</Label>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={createdSecretData?.token || ""}
                  className="bg-slate-50 font-mono text-xs select-all"
                />
                <Button
                  size="icon"
                  variant="outline"
                  onClick={() => createdSecretData && copyToClipboard(createdSecretData.token)}
                  aria-label="Copy to clipboard"
                >
                  {copied ? <Check size={16} className="text-emerald-600" /> : <Copy size={16} />}
                </Button>
              </div>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-[11px] leading-relaxed text-amber-800">
              Use this token in machine HTTP requests: <br />
              <code className="mt-1 block font-mono text-[10px] text-amber-950">
                Authorization: Bearer {createdSecretData?.token}
              </code>
            </div>

            <div className="flex justify-end pt-2">
              <Button onClick={() => setCreatedSecretData(null)}>I have copied my key</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm Revoke Dialog */}
      <ConfirmationDialog
        open={Boolean(revokingClient)}
        onOpenChange={(open) => !open && setRevokingClient(null)}
        title="Revoke API Key?"
        description={`Are you sure you want to revoke "${revokingClient?.name}"? Any service using this key will immediately fail with HTTP 401 Unauthorized.`}
        confirmLabel="Revoke Key"
        destructive
        onConfirm={handleRevokeClient}
      />

      <ConfirmationDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Remove API token?"
        description="Protected API requests from this tab will stop until you enter a client token again."
        confirmLabel="Remove token"
        destructive
        onConfirm={clear}
      />
    </>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  const confirmed = ["Operational", "ok"].includes(value);
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-3">
      <span className="text-xs text-slate-500">{label}</span>
      <Badge
        variant={
          confirmed
            ? "success"
            : value === "unavailable" || value === "Unavailable"
            ? "danger"
            : "neutral"
        }
      >
        {value}
      </Badge>
    </div>
  );
}
