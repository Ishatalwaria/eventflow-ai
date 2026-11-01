import { useState } from "react";
import { AlertCircle, BarChart3, DatabaseZap, Gauge, RefreshCw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiRequestError, apiErrorMessage } from "../../api/client";
import { useLifecycleAnalytics } from "../../api/hooks";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "../../components/layout";
import { Button, Card, Select } from "../../components/ui";
import { formatDate } from "../../lib/utils";

const SUCCESS = "#059669";
const FAILURE = "#e11d48";
const BLUE = "#2563eb";

function utcDate(daysAgo = 0) {
  return new Date(Date.now() - daysAgo * 86_400_000).toISOString().slice(0, 10);
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function minuteLabel(value: string) {
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function AnalyticsPage() {
  const { hasToken } = useAuth();
  const [dateFrom, setDateFrom] = useState(() => utcDate(6));
  const [dateTo, setDateTo] = useState(() => utcDate());
  const [rangeDays, setRangeDays] = useState("7");
  const rangeValid = dateFrom <= dateTo;
  const analytics = useLifecycleAnalytics({ date_from: dateFrom, date_to: dateTo }, hasToken && rangeValid);
  const data = analytics.data;
  const total = data ? data.success_count + data.failure_count : 0;
  const outcomes = data ? [
    { name: "Successful", value: data.success_count },
    { name: "Failed", value: data.failure_count },
  ].filter((item) => item.value > 0) : [];

  const chooseRange = (days: string) => {
    setRangeDays(days);
    const length = Number(days);
    setDateFrom(utcDate(length - 1));
    setDateTo(utcDate());
  };
  const errorDescription = analytics.error instanceof ApiRequestError && analytics.error.status === 403
    ? "This client cannot access the requested analytics report. Contact the system operator to review its access."
    : analytics.error ? apiErrorMessage(analytics.error) : "Analytics data could not be retrieved.";

  return <>
    <PageHeader eyebrow="Operational reporting" title="Analytics" description="Explore workflow lifecycle data for this API client." actions={<div className="flex flex-wrap items-center gap-2"><Select aria-label="Analytics time range" value={rangeDays} onChange={(event) => chooseRange(event.target.value)} className="w-36"><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></Select><Button variant="outline" onClick={() => void analytics.refetch()} disabled={!rangeValid || analytics.isFetching}><RefreshCw size={15} />Refresh</Button></div>} />

    <Card className="mb-5 flex flex-wrap items-center justify-between gap-4 p-4">
      <div><div className="text-xs font-semibold text-slate-800">Selected range</div><div className="mt-1 text-xs text-slate-500">Backend dates · up to 367 days</div></div>
      <div className="grid w-full gap-3 sm:w-auto sm:grid-cols-2"><label className="text-[11px] font-semibold text-slate-600">From<InputDate value={dateFrom} onChange={(value) => { setDateFrom(value); setRangeDays("custom"); }} /></label><label className="text-[11px] font-semibold text-slate-600">To<InputDate value={dateTo} onChange={(value) => { setDateTo(value); setRangeDays("custom"); }} /></label></div>
    </Card>

    {!rangeValid && <div className="mb-5"><ErrorState title="Invalid date range" description="The start date must be on or before the end date." /></div>}
    {!hasToken ? <Card><EmptyState icon={DatabaseZap} title="API connection required" description="Connect an API client in Settings to retrieve tenant-scoped analytics." /></Card>
      : rangeValid && analytics.isLoading ? <Card><LoadingState label="Loading analytics…" /></Card>
        : rangeValid && analytics.isError ? <><ErrorState title="Analytics unavailable" description={errorDescription} onRetry={() => void analytics.refetch()} />{analytics.error instanceof ApiRequestError && analytics.error.status === 403 && <Card className="mt-4 border-amber-200 bg-amber-50 p-4"><h2 className="text-sm font-semibold text-amber-950">Global analytics access</h2><p className="mt-1 text-xs leading-relaxed text-amber-900">The global ClickHouse endpoint is restricted because it includes system-wide data. Ask an operator to create a dedicated analytics reader credential, then replace the API client token in Settings. This grants system-wide read access.</p><code className="mt-3 block overflow-x-auto rounded-md bg-white px-3 py-2 text-[11px] text-slate-800">docker compose exec -T api python manage.py client_credentials create --name "analytics-reader" --analytics-access</code><p className="mt-2 text-[10px] text-amber-900">The generated secret is shown once. Regular clients continue to use tenant-scoped PostgreSQL analytics.</p></Card>}</>
          : data && <>
            {data.source === "clickhouse" ? <Card className="mb-5 flex flex-col gap-3 border-blue-100 bg-blue-50/70 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><DatabaseZap size={18} className="mt-0.5 shrink-0 text-blue-700" /><div><div className="text-sm font-semibold text-blue-950">ClickHouse data is eventually consistent</div><p className="mt-1 text-xs leading-relaxed text-blue-900">Analytics may lag behind PostgreSQL workflow state while lifecycle events are projected.</p></div></div><div className="text-xs text-blue-900">{data.data_lag_seconds === null ? "No events in range" : `Latest event ${data.data_lag_seconds}s ago`}</div></Card> : <Card className="mb-5 border-emerald-100 bg-emerald-50/70 p-4"><div className="flex items-start gap-3"><DatabaseZap size={18} className="mt-0.5 shrink-0 text-emerald-700" /><div><div className="text-sm font-semibold text-emerald-950">PostgreSQL current-state report</div><p className="mt-1 text-xs leading-relaxed text-emerald-900">Metrics are scoped to this API client and computed from the authoritative workflow database. Data can change while the report loads.</p></div></div></Card>}
            <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric title="Terminal workflows" value={total.toLocaleString()} detail={`${data.success_count.toLocaleString()} succeeded · ${data.failure_count.toLocaleString()} failed`} icon={BarChart3} />
              <Metric title="Success rate" value={percent(data.success_rate)} detail="Successful terminal workflows" icon={Gauge} tone="success" />
              <Metric title="Failure rate" value={percent(data.failure_rate)} detail="Failed or dead-lettered workflows" icon={AlertCircle} tone="failure" />
              <Metric title="Latency p95" value={data.latency_ms.p95 === null ? "Not available" : `${Math.round(data.latency_ms.p95)} ms`} detail={data.latency_ms.p50 === null ? "No latency samples in range" : `p50 ${Math.round(data.latency_ms.p50)} ms · p99 ${Math.round(data.latency_ms.p99 ?? 0)} ms`} icon={Gauge} />
            </div>

            <div className="mb-5 grid gap-5 xl:grid-cols-2">
              <ChartPanel title="Events processed per minute" subtitle="Terminal workflow lifecycle events">
                {data.processed_per_minute.length ? <ResponsiveContainer width="100%" height={260}><LineChart data={data.processed_per_minute} margin={{ top: 8, right: 14, left: 0, bottom: 4 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="minute" tickFormatter={minuteLabel} minTickGap={35} tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} width={35} tick={{ fontSize: 10 }} /><Tooltip labelFormatter={(value) => minuteLabel(String(value))} formatter={(value) => [value, "Workflows"]} /><Line type="monotone" dataKey="count" name="Workflows" stroke={BLUE} strokeWidth={2} dot={false} activeDot={{ r: 4 }} /></LineChart></ResponsiveContainer> : <ChartEmpty />}
              </ChartPanel>
              <ChartPanel title="Workflow outcomes" subtitle="Success and failure share for the selected range">
                {outcomes.length ? <div className="flex flex-col items-center gap-2 sm:flex-row"><ResponsiveContainer width="100%" height={245}><PieChart><Pie data={outcomes} dataKey="value" nameKey="name" innerRadius={62} outerRadius={92} paddingAngle={3}>{outcomes.map((entry) => <Cell key={entry.name} fill={entry.name === "Successful" ? SUCCESS : FAILURE} />)}</Pie><Tooltip formatter={(value, name) => [value, name]} /></PieChart></ResponsiveContainer><div className="min-w-40 space-y-3 text-xs">{outcomes.map((entry) => <div key={entry.name} className="flex items-center justify-between gap-5"><span className="flex items-center gap-2 text-slate-600"><i className={`h-2.5 w-2.5 rounded-full ${entry.name === "Successful" ? "bg-emerald-600" : "bg-rose-600"}`} />{entry.name}</span><strong className="text-slate-800">{entry.value.toLocaleString()}</strong></div>)}</div></div> : <ChartEmpty />}
              </ChartPanel>
              <ChartPanel title="Latency percentiles" subtitle={data.source === "postgresql" ? "End-to-end terminal workflow duration from PostgreSQL timestamps" : "Stage-attempt duration from ClickHouse lifecycle records"}>
                {data.latency_ms.p50 !== null ? <ResponsiveContainer width="100%" height={245}><BarChart data={[{ percentile: "p50", ms: data.latency_ms.p50 }, { percentile: "p95", ms: data.latency_ms.p95 ?? 0 }, { percentile: "p99", ms: data.latency_ms.p99 ?? 0 }]} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="percentile" tick={{ fontSize: 11 }} /><YAxis width={45} tick={{ fontSize: 10 }} /><Tooltip formatter={(value) => [`${value} ms`, "Latency"]} /><Bar dataKey="ms" name="Latency" fill={BLUE} radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <ChartEmpty />}
              </ChartPanel>
              <ChartPanel title="Retry count distribution" subtitle="Workflows grouped by recorded retry count">
                {data.retry_count_distribution.length ? <ResponsiveContainer width="100%" height={245}><BarChart data={data.retry_count_distribution} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="retry_count" tick={{ fontSize: 10 }} label={{ value: "Retries", position: "insideBottom", offset: -2, fontSize: 10 }} /><YAxis allowDecimals={false} width={42} tick={{ fontSize: 10 }} /><Tooltip formatter={(value) => [value, "Workflows"]} /><Bar dataKey="workflow_count" name="Workflows" fill="#7c3aed" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <ChartEmpty />}
              </ChartPanel>
              <ChartPanel title="Most frequent error codes" subtitle="Failed and dead-lettered lifecycle records">
                {data.frequent_error_codes.length ? <ResponsiveContainer width="100%" height={245}><BarChart data={data.frequent_error_codes} layout="vertical" margin={{ top: 8, right: 16, left: 16, bottom: 4 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} /><YAxis type="category" dataKey="error_code" width={140} tick={{ fontSize: 9 }} /><Tooltip formatter={(value) => [value, "Occurrences"]} /><Bar dataKey="count" name="Occurrences" fill={FAILURE} radius={[0, 5, 5, 0]} /></BarChart></ResponsiveContainer> : <ChartEmpty />}
              </ChartPanel>
              <ChartPanel title="Failure rate by workflow stage" subtitle="Failures divided by terminal workflows at each stage">
                {data.failure_rate_by_stage.length ? <ResponsiveContainer width="100%" height={245}><BarChart data={data.failure_rate_by_stage.map((stage) => ({ ...stage, rate: stage.failure_rate * 100 }))} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="stage" tick={{ fontSize: 10 }} /><YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} width={45} tick={{ fontSize: 10 }} /><Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, "Failure rate"]} /><Bar dataKey="rate" name="Failure rate" fill={FAILURE} radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <ChartEmpty />}
              </ChartPanel>
            </div>

            <Card className="p-4 sm:p-5"><div className="flex flex-col gap-2 text-xs sm:flex-row sm:items-center sm:justify-between"><span className="font-semibold text-slate-700">Data freshness</span><span className="text-slate-500">Latest analytics event: {data.latest_event_time ? formatDate(data.latest_event_time) : "No data in selected range"}</span><span className="text-slate-500">Report generated: {formatDate(data.generated_at)}</span></div></Card>
          </>}
  </>;
}

function InputDate({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 block h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-800 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500" />;
}

function Metric({ title, value, detail, icon: Icon, tone = "default" }: { title: string; value: string; detail: string; icon: typeof Gauge; tone?: "default" | "success" | "failure" }) {
  const color = tone === "success" ? "text-emerald-600 bg-emerald-50" : tone === "failure" ? "text-rose-600 bg-rose-50" : "text-blue-600 bg-blue-50";
  return <Card className="p-4"><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-slate-500">{title}</span><span className={`grid h-8 w-8 place-items-center rounded-lg ${color}`}><Icon size={16} /></span></div><div className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{value}</div><div className="mt-1 text-[11px] text-slate-500">{detail}</div></Card>;
}

function ChartPanel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <Card className="min-w-0 overflow-hidden"><div className="px-5 pt-5"><h2 className="text-sm font-bold text-slate-900">{title}</h2><p className="mt-1 text-[11px] text-slate-500">{subtitle}</p></div><div className="px-3 pb-3 pt-2">{children}</div></Card>;
}

function ChartEmpty() {
  return <div className="grid h-[245px] place-items-center"><EmptyState title="No data for this range" description="Try a wider date range or check again after new lifecycle events arrive." /></div>;
}
