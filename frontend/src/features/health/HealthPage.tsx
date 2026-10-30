import { Activity, AlertCircle, Check, Clock3, Database, HeartPulse, RefreshCw, Server, WifiOff } from "lucide-react";
import { apiErrorMessage } from "../../api/client";
import { useHealthChecks } from "../../api/hooks";
import { Badge, Button, Card } from "../../components/ui";
import { ErrorState, LoadingState, PageHeader, SectionTitle } from "../../components/layout";
import { formatDate } from "../../lib/utils";

const unavailableServices = [
  { name: "Kafka", reason: "No Kafka-specific health endpoint." },
  { name: "RabbitMQ", reason: "No RabbitMQ-specific health endpoint." },
  { name: "ClickHouse", reason: "No ClickHouse-specific health endpoint." },
  { name: "Background workers", reason: "No worker health endpoint is exposed through the API." },
  { name: "LLM provider", reason: "Provider availability is not checked by the health endpoints." },
];
const unavailableMetrics = ["API request counts and latency", "Worker processing metrics", "Retry counts", "Dead-letter counts", "Queue depth", "LLM latency and errors"];

export function HealthPage() {
  const health = useHealthChecks();
  const { live, ready } = health;
  const liveValue = live.data?.status === "ok" ? "Operational" : live.isError ? "Unavailable" : "Checking";
  const databaseStatus = ready.data?.checks?.database;
  const databaseValue = databaseStatus === "ok" ? "Ready" : databaseStatus === "unavailable" || ready.data?.status === "not_ready" || ready.isError ? "Unavailable" : "Checking";
  const apiChecked = live.dataUpdatedAt || live.errorUpdatedAt;
  const dbChecked = ready.dataUpdatedAt || ready.errorUpdatedAt;

  return <>
    <PageHeader eyebrow="Platform status" title="System health" description="Only endpoint-backed health is reported. Checks refresh every 30 seconds." actions={<Button variant="outline" onClick={health.refetch} disabled={live.isFetching || ready.isFetching}><RefreshCw size={15} className={live.isFetching || ready.isFetching ? "animate-spin" : ""} />Refresh</Button>} />
    {health.isLoading ? <Card><LoadingState label="Checking API and database readiness…" /></Card> : <>
      <div className="mb-5 grid gap-4 md:grid-cols-2"><HealthCard name="Django API" description="Process liveness" status={liveValue} checked={apiChecked} error={live.isError ? apiErrorMessage(live.error) : undefined} icon={Server} /><HealthCard name="PostgreSQL" description="Readiness database check" status={databaseValue} checked={dbChecked} error={ready.isError ? apiErrorMessage(ready.error) : databaseStatus === "unavailable" ? "Readiness check reports database unavailable." : undefined} icon={Database} /></div>
      {(live.isError || ready.isError) && <div className="mb-5"><ErrorState title="One or more health checks failed" description="The service cards show each check independently; retry the unavailable endpoint." onRetry={health.refetch} /></div>}
      <Card className="mb-5 overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Additional services" detail="No status is inferred from the API or container state." /></div><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">{unavailableServices.map(({ name, reason }) => <div key={name} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><WifiOff size={15} className="text-slate-400" />{name}</div><Badge variant="neutral">Not Available</Badge></div><p className="mt-2 text-xs leading-relaxed text-slate-500">{reason}</p></div>)}</div></Card>
      <Card className="p-5 sm:p-6"><SectionTitle title="Operational metrics" detail="Prometheus exposition requires a separate metrics credential; the browser does not request or store it." /><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{unavailableMetrics.map((metric) => <div key={metric} className="flex items-center gap-2 rounded-lg border border-slate-100 p-3 text-xs text-slate-600"><AlertCircle size={14} className="shrink-0 text-slate-400" />{metric}<span className="ml-auto text-[9px] font-bold text-slate-400">N/A</span></div>)}</div><p className="mt-4 text-[11px] leading-relaxed text-slate-500">The `/metrics` route is protected by `X-Metrics-Token`, which is separate from the tenant API client token. No metrics are displayed without a safe server-side integration.</p></Card>
    </>}
  </>;
}

function HealthCard({ name, description, status, checked, error, icon: Icon }: { name: string; description: string; status: string; checked: number; error?: string; icon: typeof Server }) {
  const ok = status === "Operational" || status === "Ready";
  return <Card className="p-5 sm:p-6"><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><Icon size={18} /></div><div><div className="text-sm font-bold text-slate-900">{name}</div><div className="mt-1 text-xs text-slate-500">{description}</div></div></div><Badge variant={ok ? "success" : status === "Unavailable" ? "danger" : "neutral"}>{status}</Badge></div><div className={"mt-5 flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs " + (ok ? "bg-emerald-50 text-emerald-800" : error ? "bg-rose-50 text-rose-800" : "bg-slate-50 text-slate-500")}>{ok ? <Check size={14} /> : error ? <HeartPulse size={14} /> : <Activity size={14} />}{error ?? (ok ? "The health endpoint confirmed this status." : "Status is not currently confirmed.")}</div><div className="mt-3 flex items-center gap-1.5 text-[10px] text-slate-400"><Clock3 size={12} />Last checked {checked ? formatDate(new Date(checked).toISOString()) : "Not checked yet"}</div></Card>;
}
