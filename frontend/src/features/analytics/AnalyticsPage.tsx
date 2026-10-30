import { AlertCircle, BarChart3, DatabaseZap, FileCode2, Gauge, Info } from "lucide-react";
import { API_BASE_URL } from "../../api/client";
import { PageHeader } from "../../components/layout";
import { Button, Card } from "../../components/ui";

const unavailableMetrics = [
  { title: "Events processed per minute", group: "Volume", icon: BarChart3 },
  { title: "Success and failure rates", group: "Outcomes", icon: Gauge },
  { title: "Processing latency p50 / p95 / p99", group: "Latency", icon: Gauge },
  { title: "Retry count distribution", group: "Retries", icon: DatabaseZap },
  { title: "Most frequent error codes", group: "Errors", icon: AlertCircle },
  { title: "Failure rate by workflow stage", group: "Stages", icon: BarChart3 },
  { title: "Latest analytics event and data freshness", group: "Freshness", icon: DatabaseZap },
];

export function AnalyticsPage() {
  const docsUrl = API_BASE_URL.replace(/\/$/, "") + "/api/docs/";
  return <>
    <PageHeader eyebrow="Operational reporting" title="Analytics" description="Review analytics coverage and data access for this backend." />
    <Card className="mb-5 overflow-hidden"><div className="grid gap-0 lg:grid-cols-[1.2fr_.8fr]"><div className="p-6 sm:p-8"><div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-blue-600"><BarChart3 size={22} /></div><div className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-800"><Info size={13} />Analytics data not available</div><h2 className="mt-4 text-lg font-bold text-slate-900">No browser-facing analytics endpoint</h2><p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">The backend’s ClickHouse report is available through the <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">analytics_report</code> management command. This UI cannot query it, so metrics and charts are not rendered.</p><div className="mt-5 rounded-xl border border-blue-100 bg-blue-50/60 p-4"><div className="text-xs font-bold text-blue-900">Eventual consistency</div><p className="mt-1 text-xs leading-relaxed text-blue-800">ClickHouse lifecycle analytics can lag behind PostgreSQL workflow state. When a reporting API is added, freshness and time range will need to be shown with each result.</p></div></div><div className="border-t border-slate-100 bg-slate-50/70 p-6 sm:p-8 lg:border-l lg:border-t-0"><div className="text-xs font-bold uppercase tracking-[.14em] text-slate-500">Data access boundary</div><div className="mt-4 space-y-3"><BoundaryRow title="ClickHouse analytics" detail="Management command only; no HTTP query endpoint." /><BoundaryRow title="Prometheus metrics" detail="GET /metrics requires a separate metrics token; it is not sent from the browser." /><BoundaryRow title="Time range filters" detail="No reporting API accepts a time-range query." /></div><Button className="mt-6" variant="outline" asChild><a href={docsUrl} target="_blank" rel="noreferrer"><FileCode2 size={15} />Open API docs</a></Button></div></div></Card>
    <div className="mb-3"><h2 className="text-sm font-bold text-slate-900">Requested analytical metrics</h2><p className="mt-1 text-xs text-slate-500">Each metric remains unavailable until a supported API returns actual data.</p></div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{unavailableMetrics.map(({ title, group, icon: Icon }) => <Card key={title} className="p-4"><div className="flex items-start justify-between gap-3"><div className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 text-slate-500"><Icon size={17} /></div><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-500">Not Available</span></div><div className="mt-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">{group}</div><h3 className="mt-1 text-sm font-semibold text-slate-800">{title}</h3><p className="mt-2 text-xs leading-relaxed text-slate-500">Cannot be retrieved from the existing browser-facing API.</p></Card>)}</div>
  </>;
}

function BoundaryRow({ title, detail }: { title: string; detail: string }) { return <div className="rounded-lg border border-slate-200 bg-white p-3"><div className="text-xs font-semibold text-slate-800">{title}</div><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{detail}</p></div>; }

