import { Activity, AlertTriangle, ArrowRight, ArrowUpRight, BarChart3, CheckCircle2, Clock3, GitBranch, HeartPulse, Inbox, Plus, RefreshCw, ShieldAlert, Workflow as WorkflowIcon } from "lucide-react";
import { useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Link } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useHealthChecks, useWorkflowStateCounts, useWorkflows } from "../../api/hooks";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, MetricCard, PageHeader, SectionTitle, StateBadge } from "../../components/layout";
import { Button, Card } from "../../components/ui";
import { compactId, formatDate, formatDuration } from "../../lib/utils";

const chartColors = ["#94a3b8", "#3b82f6", "#10b981", "#f43f5e"];

export function OverviewPage() {
  const { hasToken } = useAuth();
  const total = useWorkflows({ page_size: 1 }, hasToken);
  const recent = useWorkflows({ page: 1, page_size: 6 }, hasToken);
  const states = useWorkflowStateCounts(hasToken);
  const health = useHealthChecks();
  const fetching = total.isFetching || recent.isFetching || states.isFetching;
  const isError = total.isError || recent.isError || states.isError;
  const lastUpdated = Math.max(total.dataUpdatedAt, recent.dataUpdatedAt, states.updatedAt);
  const retry = () => { void total.refetch(); void recent.refetch(); void states.refetch(); health.refetch(); };
  const stateCounts = states.counts;
  const pendingCount = stateCounts.RECEIVED + stateCounts.QUEUED + stateCounts.RETRY_WAIT;
  const failedCount = stateCounts.FAILED;
  const statusData = useMemo(() => [
    { name: "Pending", details: "RECEIVED + QUEUED + RETRY_WAIT", value: pendingCount },
    { name: "Processing", details: "PROCESSING", value: stateCounts.PROCESSING },
    { name: "Completed", details: "SUCCEEDED", value: stateCounts.SUCCEEDED },
    { name: "Failed", details: "FAILED + DEAD_LETTERED", value: failedCount + stateCounts.DEAD_LETTERED },
  ], [pendingCount, stateCounts.PROCESSING, stateCounts.SUCCEEDED, failedCount, stateCounts.DEAD_LETTERED]);

  return <>
    <PageHeader eyebrow="Operations at a glance" title="EventFlow AI Overview" description="Monitor events, workflows, and operational intelligence." actions={<><span className="hidden text-[11px] text-slate-400 sm:inline">Last updated {lastUpdated ? formatDate(new Date(lastUpdated).toISOString()) : "—"}</span><Button variant="outline" onClick={retry} disabled={!hasToken || fetching}><RefreshCw size={15} className={fetching ? "animate-spin" : ""} />Refresh</Button><Button asChild><Link to="/events"><Plus size={16} />Send an event</Link></Button></>} />
    {!hasToken ? <Card><EmptyState icon={Activity} title="Connect to your EventFlow API" description="Add your API client token in Settings to load live workflow data." action={<Button asChild><Link to="/settings">Open settings</Link></Button>} /></Card> : isError ? <ErrorState description={apiErrorMessage(total.error ?? recent.error ?? states.error)} onRetry={retry} /> : <>
      {total.isLoading || states.isLoading ? <KpiSkeleton /> : <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard title="Total events" value="—" note="Event list/count API unavailable" icon={Inbox} tone="slate" unavailable />
        <MetricCard title="Processed events" value="—" note="Analytics HTTP API unavailable" icon={Activity} tone="slate" unavailable />
        <MetricCard title="Successful workflows" value={stateCounts.SUCCEEDED.toLocaleString()} note="Current state: SUCCEEDED" icon={CheckCircle2} tone="emerald" />
        <MetricCard title="Failed workflows" value={failedCount.toLocaleString()} note="Current state: FAILED" icon={ShieldAlert} tone="rose" />
        <MetricCard title="Pending workflows" value={pendingCount.toLocaleString()} note="RECEIVED + QUEUED + RETRY_WAIT" icon={Clock3} tone="amber" />
        <MetricCard title="Avg. processing latency" value="—" note="No aggregate latency API" icon={BarChart3} tone="slate" unavailable />
      </div>}

      <div className="mb-5 grid gap-5 xl:grid-cols-[1.4fr_.9fr]">
        <Card className="overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Event processing activity" detail="Processed events over time" /></div><UnavailableChart icon={BarChart3} title="Activity series is not exposed by the backend" description="The backend has no event-list or analytics HTTP endpoint. This chart will appear when a read-only time-series API is available." /></Card>
        <Card className="overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Workflow status distribution" detail="Live counts from the paginated workflow API" /></div>{states.isLoading ? <ChartSkeleton /> : <div className="px-5 pb-5 sm:px-6"><div className="h-[190px] w-full">{statusData.some((item) => item.value > 0) ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={82} paddingAngle={3} stroke="none">{statusData.map((entry, index) => <Cell key={entry.name} fill={chartColors[index]} />)}</Pie><Tooltip content={<StatusTooltip />} /></PieChart></ResponsiveContainer> : <div className="grid h-full place-items-center text-xs text-slate-400">No workflows in the current account.</div>}</div><div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-2">{statusData.map((item, index) => <div key={item.name} className="flex items-center justify-between gap-2 text-[11px]"><span className="flex min-w-0 items-center gap-2 text-slate-500"><span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartColors[index] }} />{item.name}</span><strong className="text-slate-800">{item.value.toLocaleString()}</strong></div>)}</div><p className="mt-3 text-[9px] leading-relaxed text-slate-400">Pending groups RECEIVED, QUEUED, RETRY_WAIT. Failed includes FAILED and DEAD_LETTERED.</p></div>}</Card>
      </div>

      <div className="mb-5 grid gap-5 xl:grid-cols-[1.35fr_.65fr]">
        <Card className="overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Recent workflow executions" detail="Latest six workflows from the backend" action={<Link className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600" to="/workflows">View all <ArrowRight size={14} /></Link>} /></div>{recent.isLoading ? <TableSkeleton rows={4} /> : recent.data?.results.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Workflow</th><th>Event</th><th>State</th><th>Created</th><th>Attempt time</th><th></th></tr></thead><tbody>{recent.data.results.map((workflow) => { const durations = workflow.attempts.map((attempt) => attempt.duration_ms).filter((value): value is number => value !== null); const attemptTime = durations.length ? durations.reduce((sum, value) => sum + value, 0) : null; return <tr key={workflow.id}><td><Link className="font-semibold text-slate-800 hover:text-blue-700" to={"/workflows/" + workflow.id}>{compactId(workflow.id, 13)}</Link></td><td><Link className="text-slate-500 hover:text-blue-700" to={"/events/" + workflow.event_id}>{compactId(workflow.event_id, 13)}</Link></td><td><StateBadge state={workflow.state} /></td><td>{formatDate(workflow.created_at)}</td><td>{formatDuration(attemptTime)}</td><td><Link aria-label="Open workflow details" to={"/workflows/" + workflow.id} className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-blue-50 hover:text-blue-600"><ArrowUpRight size={15} /></Link></td></tr>; })}</tbody></table></div> : <EmptyState icon={WorkflowIcon} title="No workflows yet" description="Submit an event to create a workflow." action={<Button asChild><Link to="/events"><Plus size={15} />Create event</Link></Button>} />}</Card>
        <Card className="overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Recent events" detail="Event discovery is unavailable" /></div><UnavailableChart icon={Inbox} title="No event list endpoint" description="Events can be retrieved by known UUID, and this tab can show its own submissions. The API cannot provide a recent event feed." compact /></Card>
      </div>

      <Card className="overflow-hidden"><div className="p-5 pb-0 sm:p-6"><SectionTitle title="Operational alerts" detail="Only backend-exposed signals are shown" /></div><div className="grid gap-3 p-5 pt-2 sm:grid-cols-2 xl:grid-cols-4 sm:p-6 sm:pt-3"><AlertItem icon={ShieldAlert} title="Failed workflows" value={failedCount.toLocaleString()} detail="State count from workflow API" tone={failedCount ? "danger" : "success"} /><AlertItem icon={AlertTriangle} title="Dead-lettered" value={stateCounts.DEAD_LETTERED.toLocaleString()} detail="Terminal dead-letter state" tone={stateCounts.DEAD_LETTERED ? "danger" : "success"} /><AlertItem icon={GitBranch} title="Outbox backlog" value="Unavailable" detail="No outbox status endpoint" tone="neutral" /><HealthAlert liveStatus={health.live.data?.status} readyStatus={health.ready.data?.checks?.database} unavailable={Boolean(health.error)} /></div></Card>
      <div className="mt-4 flex items-center justify-between text-[10px] text-slate-400"><span>Workflow metrics reflect current state counts, not event volume.</span><span>Last updated {lastUpdated ? formatDate(new Date(lastUpdated).toISOString()) : "—"}</span></div>
    </>}
  </>;
}

function KpiSkeleton() { return <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{Array.from({ length: 6 }, (_, index) => <Card key={index} className="animate-pulse p-4"><div className="h-3 w-24 rounded bg-slate-100" /><div className="mt-4 h-7 w-16 rounded bg-slate-100" /><div className="mt-3 h-2 w-32 rounded bg-slate-50" /></Card>)}</div>; }
function ChartSkeleton() { return <div className="m-6 h-[190px] animate-pulse rounded-xl bg-slate-50" />; }
function TableSkeleton({ rows }: { rows: number }) { return <div className="space-y-4 p-6">{Array.from({ length: rows }, (_, index) => <div key={index} className="flex animate-pulse gap-4"><div className="h-3 flex-1 rounded bg-slate-100" /><div className="h-3 w-20 rounded bg-slate-100" /><div className="h-3 w-24 rounded bg-slate-100" /></div>)}</div>; }

function UnavailableChart({ icon: Icon, title, description, compact = false }: { icon: typeof BarChart3; title: string; description: string; compact?: boolean }) {
  return <div className={"flex flex-col items-center justify-center px-6 text-center " + (compact ? "py-8" : "h-[255px]")}><div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-400"><Icon size={18} /></div><h3 className="text-xs font-bold text-slate-700">{title}</h3><p className="mt-1 max-w-sm text-[10px] leading-relaxed text-slate-400">{description}</p></div>;
}

function StatusTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { name: string; details: string; value: number } }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg"><div className="text-xs font-bold text-slate-800">{item.name}: {item.value.toLocaleString()}</div><div className="mt-1 text-[9px] text-slate-500">States: {item.details}</div></div>;
}

function AlertItem({ icon: Icon, title, value, detail, tone }: { icon: typeof AlertTriangle; title: string; value: string; detail: string; tone: "danger" | "success" | "neutral" }) {
  const color = tone === "danger" ? "text-rose-700 bg-rose-50" : tone === "success" ? "text-emerald-700 bg-emerald-50" : "text-slate-600 bg-slate-100";
  return <div className="rounded-xl border border-slate-100 p-3.5"><div className="flex items-center gap-2"><div className={"grid h-7 w-7 place-items-center rounded-lg " + color}><Icon size={14} /></div><span className="text-[11px] font-bold text-slate-700">{title}</span></div><div className="mt-3 text-lg font-bold text-slate-900">{value}</div><div className="mt-1 text-[9px] text-slate-400">{detail}</div></div>;
}

function HealthAlert({ liveStatus, readyStatus, unavailable }: { liveStatus?: string; readyStatus?: string; unavailable: boolean }) {
  const ok = liveStatus === "ok" && readyStatus === "ok";
  const value = unavailable ? "Unavailable" : ok ? "Ready" : "Checking";
  return <AlertItem icon={HeartPulse} title="API / database" value={value} detail="Liveness and PostgreSQL readiness only" tone={unavailable ? "neutral" : ok ? "success" : "danger"} />;
}

