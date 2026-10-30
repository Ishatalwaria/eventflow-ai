import { useQueries } from "@tanstack/react-query";
import { ArrowUpRight, Search, Workflow as WorkflowIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useWorkflows } from "../../api/hooks";
import { workflowsService } from "../../api/services/workflows";
import type { Workflow, WorkflowState } from "../../api/types";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, StateBadge } from "../../components/layout";
import { Button, Card, Input, Select } from "../../components/ui";
import { compactId, formatDate } from "../../lib/utils";

const PAGE_SIZE = 50;
const STATE_PAGE_SIZE = 100;
const groups = {
  all: null,
  pending: ["RECEIVED", "QUEUED", "RETRY_WAIT"],
  processing: ["PROCESSING"],
  completed: ["SUCCEEDED"],
  failed: ["FAILED", "DEAD_LETTERED"],
} as const satisfies Record<string, readonly WorkflowState[] | null>;
type Group = keyof typeof groups;

export function WorkflowsPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const rawGroup = params.get("state") ?? "all";
  const group: Group = rawGroup in groups ? rawGroup as Group : "all";
  const { hasToken } = useAuth();
  const allQuery = useWorkflows({ page, page_size: PAGE_SIZE }, hasToken && group === "all");
  const selectedStates = groups[group] ?? [];
  const sourcePages = Math.ceil(page * PAGE_SIZE / STATE_PAGE_SIZE);
  const groupedQueries = useQueries({ queries: selectedStates.flatMap((state) => Array.from({ length: sourcePages }, (_, index) => ({ queryKey: ["workflows", "group", group, state, index + 1], queryFn: () => workflowsService.list({ state, page: index + 1, page_size: STATE_PAGE_SIZE }), enabled: hasToken && group !== "all" }))) });
  const items: Workflow[] = useMemo(() => group === "all" ? allQuery.data?.results ?? [] : groupedQueries.flatMap((query) => query.data?.results ?? []).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [group, allQuery.data, groupedQueries, page]);
  const filtered = useMemo(() => items.filter((item) => [item.id, item.event_id, item.current_stage, item.last_error_code].join(" ").toLowerCase().includes(search.toLowerCase())), [items, search]);
  const groupedCount = selectedStates.reduce((sum, _state, index) => sum + (groupedQueries[index * sourcePages]?.data?.count ?? 0), 0);
  const count = group === "all" ? allQuery.data?.count ?? 0 : groupedCount;
  const loading = group === "all" ? allQuery.isLoading : groupedQueries.some((query) => query.isLoading);
  const error = group === "all" ? allQuery.error : groupedQueries.find((query) => query.isError)?.error;
  const fetching = group === "all" ? allQuery.isFetching : groupedQueries.some((query) => query.isFetching);
  const refresh = () => { if (group === "all") void allQuery.refetch(); else groupedQueries.forEach((query) => void query.refetch()); };
  const setGroup = (value: string) => setParams((old) => { const next = new URLSearchParams(old); if (value === "all") next.delete("state"); else next.set("state", value); next.delete("page"); return next; });
  return <>
    <PageHeader eyebrow="Execution" title="Workflow monitoring" description="Track orchestration state, processing stages, and recorded attempts." actions={<Button variant="outline" onClick={refresh} disabled={!hasToken || fetching}><WorkflowIcon size={15} />Refresh</Button>} />
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5"><div className="relative w-full sm:max-w-xs"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflow or event ID…" className="h-9 pl-9" aria-label="Search workflows" /></div><Select aria-label="Filter workflow state group" className="h-9 w-full sm:w-56" value={group} onChange={(event) => setGroup(event.target.value)}><option value="all">All workflows</option><option value="pending">Pending · received, queued, retry wait</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="failed">Failed · failed, dead lettered</option></Select></div>
      {!hasToken ? <EmptyState icon={WorkflowIcon} title="API connection required" description="Connect a client token in Settings to browse workflows." /> : loading ? <LoadingState /> : error ? <div className="p-5"><ErrorState description={apiErrorMessage(error)} onRetry={refresh} /></div> : !items.length ? <EmptyState icon={WorkflowIcon} title="No workflows found" description="No workflows match this state filter." /> : !filtered.length ? <EmptyState icon={Search} title="No matches on this page" description="Try another workflow or event ID." /> : <>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>Workflow ID</th><th>Event ID</th><th>State</th><th>Current stage</th><th>Created</th><th>Updated</th><th>Attempts</th><th /></tr></thead><tbody>{filtered.map((workflow) => <tr key={workflow.id}><td><Link to={`/workflows/${workflow.id}`} className="font-mono font-semibold text-blue-700 hover:underline">{compactId(workflow.id, 13)}</Link></td><td><Link to={`/events/${workflow.event_id}`} className="font-mono text-slate-600 hover:text-blue-700">{compactId(workflow.event_id, 13)}</Link></td><td><StateBadge state={workflow.state} /></td><td className="capitalize">{workflow.current_stage.replaceAll("_", " ") || "—"}</td><td>{formatDate(workflow.created_at)}</td><td>{formatDate(workflow.updated_at)}</td><td>{workflow.attempts.length}</td><td><Link aria-label={`View workflow ${workflow.id}`} to={`/workflows/${workflow.id}`} className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-blue-50 hover:text-blue-600"><ArrowUpRight size={16} /></Link></td></tr>)}</tbody></table></div>
        <Pagination page={page} count={count} pageSize={PAGE_SIZE} onPageChange={(value) => setParams((old) => { const next = new URLSearchParams(old); if (value === 1) next.delete("page"); else next.set("page", String(value)); return next; })} />
      </>}
    </Card>
  </>;
}

