import { Activity, AlertCircle, Check, Clock3, Database, RefreshCw, Server, WifiOff } from "lucide-react";
import { Link } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useHealthChecks, useServiceHealth } from "../../api/hooks";
import { useAuth } from "../../app/auth";
import { ErrorState, LoadingState, PageHeader, SectionTitle } from "../../components/layout";
import { Badge, Button, Card } from "../../components/ui";
import { formatDate } from "../../lib/utils";

export function HealthPage() {
  const { hasToken } = useAuth();
  const health = useHealthChecks();
  const summary = useServiceHealth(hasToken);
  const busy = summary.isFetching;
  const refresh = () => { void summary.refetch(); health.refetch(); };
  const metrics = summary.data?.metrics;
  const unavailableMetrics = metrics?.availability === "unavailable";

  return <>
    <PageHeader eyebrow="Platform status" title="System health" description="Service probes and approved operational metrics refresh every 30 seconds." actions={<Button variant="outline" onClick={refresh} disabled={busy}><RefreshCw size={15} className={busy ? "animate-spin" : ""} />Refresh</Button>} />
    {!hasToken ? <Card className="p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-sm font-bold text-slate-900">Connect an API client for service checks</h2><p className="mt-1 text-xs text-slate-500">The detailed health summary is authenticated. Basic API liveness and PostgreSQL readiness remain public.</p></div><Button asChild><Link to="/settings">Open settings</Link></Button></div><div className="mt-5 grid gap-4 md:grid-cols-2"><BasicCard name="Django API" status={health.live.data?.status === "ok" ? "healthy" : health.live.isError ? "unavailable" : "not_checked"} detail="Public process liveness check" checked={health.live.dataUpdatedAt} icon={Server} /><BasicCard name="PostgreSQL" status={health.ready.data?.checks?.database === "ok" ? "healthy" : health.ready.isError ? "unavailable" : "not_checked"} detail="Public database readiness check" checked={health.ready.dataUpdatedAt} icon={Database} /></div></Card>
      : summary.isLoading ? <Card><LoadingState label="Checking configured services and metrics…" /></Card>
        : summary.isError ? <ErrorState title="Health summary unavailable" description={apiErrorMessage(summary.error)} onRetry={refresh} />
          : summary.data && metrics && <>
            <Card className="mb-5 overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Service status" detail="Checks run from the Django API using server-side service credentials." /></div><div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">{summary.data.services.map((service) => <div key={service.name} className="rounded-xl border border-slate-200 bg-white p-4"><div className="flex items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-800">{service.status === "healthy" ? <Check size={15} className="shrink-0 text-emerald-600" /> : service.status === "unavailable" ? <WifiOff size={15} className="shrink-0 text-rose-500" /> : <AlertCircle size={15} className="shrink-0 text-slate-400" />}{service.name}</div><StatusBadge status={service.status} /></div><p className="mt-2 min-h-8 text-xs leading-relaxed text-slate-500">{service.detail}</p><div className="mt-3 flex items-center gap-1.5 text-[10px] text-slate-400"><Clock3 size={12} />{service.last_checked ? `Last checked ${formatDate(service.last_checked)}` : "Not checked"}</div></div>)}</div></Card>
            <Card className="p-5 sm:p-6"><SectionTitle title="Operational metrics" detail="Values are shown only when the private server-side metrics source has samples." />{unavailableMetrics && <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{metrics.detail ?? "Metrics could not be retrieved."}</p>}<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[
              ["API requests", metrics.api_requests_total, "Requests across API and worker process metrics"],
              ["Average API request latency", metrics.api_average_latency_ms, "Milliseconds from observed HTTP request durations", "ms"],
              ["Worker attempts (24h)", metrics.worker_attempts_total, "Workflow attempts persisted in PostgreSQL during the last 24 hours"],
              ["Retries (24h)", metrics.retry_count, "Retrying attempts persisted in PostgreSQL during the last 24 hours"],
              ["Dead-lettered attempts (24h)", metrics.dead_letter_count, "Dead-lettered workflow attempts persisted in PostgreSQL during the last 24 hours"],
              ["Task queue depth", metrics.task_queue_depth, "RabbitMQ task queue messages"],
              ["Dead-letter queue depth", metrics.dead_letter_queue_depth, "RabbitMQ dead-letter queue messages"],
              ["LLM errors", metrics.llm_error_count, "Provider errors observed by this API process since it started"],
              ["Average LLM latency", metrics.llm_average_latency_ms, "Requires at least one observed provider request; no health-check request is sent", "ms"],
            ].map(([label, value, detail, unit]) => <Metric key={String(label)} label={String(label)} value={typeof value === "number" ? `${formatMetric(value)}${unit ? ` ${unit}` : ""}` : "Not available"} detail={String(detail)} unavailable={typeof value !== "number"} />)}</div><p className="mt-4 text-[11px] leading-relaxed text-slate-500">Worker metrics are requested only by the backend with its configured metrics credential. The browser never receives that credential or raw Prometheus output. LLM provider availability is not probed to avoid a billable request.</p></Card>
            <p className="mt-4 text-right text-[10px] text-slate-400">Summary generated {formatDate(summary.data.generated_at)}</p>
          </>}
  </>;
}

function formatMetric(value: number) { return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1); }
function StatusBadge({ status }: { status: "healthy" | "unavailable" | "not_checked" }) { const variant = status === "healthy" ? "success" : status === "unavailable" ? "danger" : "neutral"; const label = status === "healthy" ? "Operational" : status === "unavailable" ? "Unavailable" : "Not checked"; return <Badge variant={variant}>{label}</Badge>; }
function BasicCard({ name, status, detail, checked, icon: Icon }: { name: string; status: "healthy" | "unavailable" | "not_checked"; detail: string; checked: number; icon: typeof Server }) { return <div className="rounded-xl border border-slate-200 p-4"><div className="flex items-center justify-between"><span className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Icon size={15} />{name}</span><StatusBadge status={status} /></div><p className="mt-2 text-xs text-slate-500">{detail}</p><p className="mt-3 text-[10px] text-slate-400">{checked ? `Last checked ${formatDate(new Date(checked).toISOString())}` : "Not checked yet"}</p></div>; }
function Metric({ label, value, detail, unavailable }: { label: string; value: string; detail: string; unavailable: boolean }) { return <div className="rounded-xl border border-slate-100 p-4"><div className="flex items-start justify-between gap-3"><div><div className="text-xs font-semibold text-slate-700">{label}</div><div className="mt-1 text-[10px] leading-relaxed text-slate-400">{detail}</div></div><Activity size={15} className={unavailable ? "text-slate-300" : "text-blue-600"} /></div><div className="mt-3 text-lg font-bold text-slate-900">{value}</div></div>; }
