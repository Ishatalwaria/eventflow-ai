import { AlertTriangle, ArrowUpRight, Bot, Search, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useWorkflows } from "../../api/hooks";
import type { WorkflowState } from "../../api/types";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, StateBadge } from "../../components/layout";
import { Button, Card, Input, Select } from "../../components/ui";
import { compactId, formatDate } from "../../lib/utils";

const PAGE_SIZE = 50;
export function IncidentsPage() {
  const [state, setState] = useState<"FAILED" | "DEAD_LETTERED">("FAILED");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const { hasToken } = useAuth();
  const query = useWorkflows({ state: state as WorkflowState, page, page_size: PAGE_SIZE }, hasToken);
  const visible = query.data?.results.filter((workflow) => (workflow.id + " " + workflow.event_id + " " + workflow.current_stage + " " + workflow.last_error_code).toLowerCase().includes(search.toLowerCase())) ?? [];
  return <>
    <PageHeader eyebrow="Failure investigation" title="AI incidents" description="Investigate terminal failures and request evidence-grounded analysis. The backend does not expose incident history, so this page lists workflows eligible for investigation." actions={<Button variant="outline" onClick={() => void query.refetch()}><Bot size={15} />Refresh</Button>} />
    <Card className="overflow-hidden"><div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5"><div className="relative w-full sm:max-w-xs"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search workflow or event ID…" aria-label="Search failed workflows" className="pl-9" /></div><div className="flex items-center gap-3"><span className="text-xs text-slate-500">Workflow state</span><Select className="w-full sm:w-52" aria-label="Filter by failed workflow state" value={state} onChange={(event) => { setState(event.target.value as "FAILED" | "DEAD_LETTERED"); setPage(1); }}><option value="FAILED">Failed</option><option value="DEAD_LETTERED">Dead lettered</option></Select></div></div>
      {!hasToken ? <EmptyState icon={AlertTriangle} title="API connection required" description="Connect a client token in Settings to inspect failed workflows." /> : query.isLoading ? <LoadingState label="Loading failed workflows…" /> : query.isError ? <div className="p-5"><ErrorState description={apiErrorMessage(query.error)} onRetry={() => void query.refetch()} /></div> : query.data?.results.length === 0 ? <EmptyState icon={ShieldAlert} title="No eligible workflows" description={"No workflows are currently in the " + state.replaceAll("_", " ") + " state."} /> : !visible.length ? <EmptyState icon={Search} title="No matching workflows" description="Try a different workflow or event ID." /> : <><div className="table-scroll"><table className="data-table"><thead><tr><th>Workflow / event</th><th>Status</th><th>Failed stage</th><th>Error code</th><th>Attempts</th><th>Updated</th><th>Incident history</th><th></th></tr></thead><tbody>{visible.map((workflow) => <tr key={workflow.id}><td><Link to={"/workflows/" + workflow.id} className="font-semibold text-slate-800 hover:text-blue-700">{compactId(workflow.id, 13)}</Link><div className="mt-1 text-[10px] text-slate-400">Event {compactId(workflow.event_id, 13)}</div></td><td><StateBadge state={workflow.state} /></td><td className="capitalize">{workflow.current_stage.replaceAll("_", " ")}</td><td className="font-mono text-[11px] text-rose-700">{workflow.last_error_code || "—"}</td><td>{workflow.attempts.length}</td><td>{formatDate(workflow.updated_at)}</td><td className="text-slate-400">Not exposed by API</td><td><Button size="sm" variant="outline" asChild><Link to={`/incidents/workflow/${workflow.id}`}>Investigate <ArrowUpRight size={14} /></Link></Button></td></tr>)}</tbody></table></div><Pagination page={page} count={query.data?.count ?? 0} pageSize={PAGE_SIZE} onPageChange={setPage} /></>}
    </Card>
    <div className="mt-5 flex items-start gap-3 rounded-xl border border-violet-100 bg-violet-50/60 p-4"><Bot size={17} className="mt-0.5 shrink-0 text-violet-600" /><p className="text-xs leading-relaxed text-violet-900">Open a workflow to review its recorded attempts and request an AI incident summary. The summary uses bounded, sanitized evidence and never changes workflow state.</p></div>
  </>;
}

