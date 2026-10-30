import { ArrowLeft, Clipboard, GitBranch } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { apiErrorMessage } from "../../api/client";
import { useEvent } from "../../api/hooks";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader, StateBadge } from "../../components/layout";
import { Button, Card } from "../../components/ui";
import { formatDate } from "../../lib/utils";

export function EventDetailPage() {
  const { eventId = "" } = useParams();
  const { hasToken } = useAuth();
  const query = useEvent(eventId, hasToken);
  const [copying, setCopying] = useState("");
  const copy = async (key: string, value: string) => {
    try { await navigator.clipboard.writeText(value); setCopying(key); toast.success("Copied to clipboard."); window.setTimeout(() => setCopying(""), 1200); }
    catch { toast.error("Clipboard access is unavailable in this browser."); }
  };
  return <>
    <PageHeader eyebrow="Event record" title="Event details" description="Complete metadata returned by the tenant-scoped event detail API." actions={<Button variant="outline" asChild><Link to="/events"><ArrowLeft size={15} />Back to events</Link></Button>} />
    {!hasToken ? <Card><EmptyState title="API connection required" description="Connect a client token in Settings to view this event." /></Card> : query.isLoading ? <Card><LoadingState label="Loading event details…" /></Card> : query.isError ? <ErrorState description={apiErrorMessage(query.error)} onRetry={() => void query.refetch()} /> : query.data ? <div className="grid gap-5 xl:grid-cols-[1fr_.85fr]">
      <Card className="p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs font-bold uppercase tracking-wider text-blue-600">{query.data.event_type} · v{query.data.schema_version}</div><h2 className="mt-2 break-all font-mono text-sm font-semibold text-slate-900">{query.data.id}</h2></div><div className="flex items-center gap-2"><StateBadge state={query.data.workflow.state} /><Button size="sm" variant="outline" onClick={() => void copy("id", query.data!.id)}><Clipboard size={14} />{copying === "id" ? "Copied" : "Copy ID"}</Button></div></div>
        <dl className="mt-6 grid gap-x-6 gap-y-4 border-t border-slate-100 pt-5 sm:grid-cols-2">{[["Source", query.data.source], ["Idempotency key", query.data.idempotency_key], ["Correlation ID", query.data.correlation_id], ["Request ID", query.data.request_id], ["Occurred at", formatDate(query.data.occurred_at)], ["Received at", formatDate(query.data.received_at)]].map(([label, value]) => <div key={label}><dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</dt><dd className="mt-1 break-all text-xs font-medium text-slate-700">{value}</dd></div>)}</dl>
        <Link to={`/workflows/${query.data.workflow.id}`} className="mt-6 flex items-center gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-4 hover:bg-blue-50"><span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-blue-600"><GitBranch size={17} /></span><span className="min-w-0 flex-1"><span className="block text-xs font-bold text-slate-800">Related workflow</span><span className="mt-1 block break-all font-mono text-[10px] text-slate-500">{query.data.workflow.id}</span></span><StateBadge state={query.data.workflow.state} /></Link>
      </Card>
      <Card className="overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><h2 className="text-sm font-bold text-slate-900">Event payload</h2><p className="mt-1 text-xs text-slate-500">Sensitive business data is shown only on this detail view.</p></div><Button size="sm" variant="outline" onClick={() => void copy("payload", JSON.stringify(query.data!.payload, null, 2))}><Clipboard size={14} />{copying === "payload" ? "Copied" : "Copy JSON"}</Button></div><pre className="max-h-[70vh] overflow-auto bg-slate-950 p-5 text-xs leading-relaxed text-slate-200">{JSON.stringify(query.data.payload, null, 2)}</pre></Card>
    </div> : null}
  </>;
}
