import { useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, Bot, Search, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { apiErrorMessage } from "../../api/client";
import { useIncidentSummaries, useWorkflows } from "../../api/hooks";
import type { WorkflowState } from "../../api/types";
import { useAuth } from "../../app/auth";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, StateBadge } from "../../components/layout";
import { Button, Card, DataTable, Input, Select } from "../../components/ui";
import { compactId, formatDate } from "../../lib/utils";

const INCIDENT_PAGE_SIZE = 10;
const WORKFLOW_PAGE_SIZE = 50;

export function IncidentsPage() {
  const [incidentSearch, setIncidentSearch] = useState("");
  const [debouncedIncidentSearch, setDebouncedIncidentSearch] = useState("");
  const [incidentState, setIncidentState] = useState<"all" | "FAILED" | "DEAD_LETTERED">("all");
  const [incidentPage, setIncidentPage] = useState(1);
  const [workflowState, setWorkflowState] = useState<"FAILED" | "DEAD_LETTERED">("FAILED");
  const [workflowPage, setWorkflowPage] = useState(1);
  const [workflowSearch, setWorkflowSearch] = useState("");
  const { hasToken } = useAuth();
  const incidents = useIncidentSummaries({
    page: incidentPage,
    page_size: INCIDENT_PAGE_SIZE,
    ...(debouncedIncidentSearch ? { search: debouncedIncidentSearch } : {}),
    ...(incidentState !== "all" ? { workflow_state: incidentState } : {}),
  }, hasToken);
  const workflows = useWorkflows({ state: workflowState as WorkflowState, page: workflowPage, page_size: WORKFLOW_PAGE_SIZE }, hasToken);
  const visibleWorkflows = workflows.data?.results.filter((workflow) =>
    (workflow.id + " " + workflow.event_id + " " + workflow.current_stage + " " + workflow.last_error_code)
      .toLowerCase().includes(workflowSearch.toLowerCase()),
  ) ?? [];

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedIncidentSearch(incidentSearch.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [incidentSearch]);

  const refresh = () => { void incidents.refetch(); void workflows.refetch(); };
  const hasIncidentFilters = Boolean(debouncedIncidentSearch) || incidentState !== "all";

  return <>
    <PageHeader eyebrow="Failure investigation" title="AI incidents" description="Review saved evidence-based analyses or investigate a failed workflow." actions={<Button variant="outline" onClick={refresh} disabled={incidents.isFetching || workflows.isFetching}><Bot size={15} />Refresh</Button>} />

    <Card className="mb-5 overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div><h2 className="text-sm font-bold text-slate-900">Incident history</h2><p className="mt-1 text-xs text-slate-500">Persisted analyses available to this API client.</p></div>
        <div className="grid gap-2 sm:grid-cols-[minmax(14rem,1fr)_12rem]">
          <Input value={incidentSearch} onChange={(event) => { setIncidentSearch(event.target.value); setIncidentPage(1); }} placeholder="Search incident, workflow, event…" aria-label="Search incidents" />
          <Select aria-label="Filter incident workflow state" value={incidentState} onChange={(event) => { setIncidentState(event.target.value as typeof incidentState); setIncidentPage(1); }}><option value="all">All states</option><option value="FAILED">Failed</option><option value="DEAD_LETTERED">Dead lettered</option></Select>
        </div>
      </div>
      {!hasToken ? <EmptyState title="API connection required" description="Connect a client token in Settings to view saved incident analyses." />
        : incidents.isLoading ? <LoadingState label="Loading incident history…" />
          : incidents.isError ? <div className="p-5"><ErrorState title="Incident history unavailable" description={apiErrorMessage(incidents.error)} onRetry={() => void incidents.refetch()} /></div>
            : !incidents.data?.results.length ? <EmptyState icon={ShieldAlert} title={hasIncidentFilters ? "No matching incidents" : "No saved incidents yet"} description={hasIncidentFilters ? "Adjust the search or state filter." : "Analyses appear here after they are generated for a failed workflow."} />
              : <DataTable rows={incidents.data.results} rowKey={(incident) => incident.id} columns={[
                { key: "id", header: "Incident ID", cell: (incident) => <Link to={`/incidents/id/${incident.id}`} className="font-mono text-blue-700 hover:underline">{compactId(incident.id, 13)}</Link> },
                { key: "workflow", header: "Workflow / event", cell: (incident) => <><Link to={`/workflows/${incident.workflow_id}`} className="font-mono text-slate-800 hover:text-blue-700">{compactId(incident.workflow_id, 13)}</Link><div className="mt-1 font-mono text-[10px] text-slate-400">{compactId(incident.event_id, 13)}</div></> },
                { key: "headline", header: "Incident", cell: (incident) => incident.headline, className: "max-w-sm font-medium text-slate-800" },
                { key: "created", header: "Created", cell: (incident) => formatDate(incident.created_at) },
                { key: "state", header: "Workflow state", cell: (incident) => <StateBadge state={incident.workflow_state} /> },
                { key: "provider", header: "Analysis", cell: (incident) => <span className="text-xs text-slate-600">{incident.provider} · {incident.model}</span> },
                { key: "action", header: "", cell: (incident) => <Link to={`/incidents/id/${incident.id}`} className="font-semibold text-blue-700 hover:underline">Review</Link> },
              ]} />}
      {!!incidents.data?.count && <Pagination page={incidentPage} count={incidents.data.count} pageSize={INCIDENT_PAGE_SIZE} onPageChange={setIncidentPage} />}
    </Card>

    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div><h2 className="text-sm font-bold text-slate-900">Workflows eligible for analysis</h2><p className="mt-1 text-xs text-slate-500">Request a new analysis for a failed or dead-lettered workflow.</p></div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center"><div className="relative w-full sm:w-64"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={workflowSearch} onChange={(event) => { setWorkflowSearch(event.target.value); setWorkflowPage(1); }} placeholder="Search workflow or event ID…" aria-label="Search failed workflows" className="pl-9" /></div><Select className="w-full sm:w-48" aria-label="Filter by failed workflow state" value={workflowState} onChange={(event) => { setWorkflowState(event.target.value as typeof workflowState); setWorkflowPage(1); }}><option value="FAILED">Failed</option><option value="DEAD_LETTERED">Dead lettered</option></Select></div>
      </div>
      {!hasToken ? <EmptyState icon={AlertTriangle} title="API connection required" description="Connect a client token in Settings to inspect failed workflows." /> : workflows.isLoading ? <LoadingState label="Loading failed workflows…" /> : workflows.isError ? <div className="p-5"><ErrorState description={apiErrorMessage(workflows.error)} onRetry={() => void workflows.refetch()} /></div> : workflows.data?.results.length === 0 ? <EmptyState icon={ShieldAlert} title="No eligible workflows" description={`No workflows are currently in the ${workflowState.replaceAll("_", " ")} state.`} /> : !visibleWorkflows.length ? <EmptyState icon={Search} title="No matching workflows" description="Try a different workflow or event ID." /> : <><div className="table-scroll"><table className="data-table"><thead><tr><th>Workflow / event</th><th>Status</th><th>Failed stage</th><th>Error code</th><th>Attempts</th><th>Updated</th><th></th></tr></thead><tbody>{visibleWorkflows.map((workflow) => <tr key={workflow.id}><td><Link to={`/workflows/${workflow.id}`} className="font-semibold text-slate-800 hover:text-blue-700">{compactId(workflow.id, 13)}</Link><div className="mt-1 text-[10px] text-slate-400">Event {compactId(workflow.event_id, 13)}</div></td><td><StateBadge state={workflow.state} /></td><td className="capitalize">{workflow.current_stage.replaceAll("_", " ")}</td><td className="font-mono text-[11px] text-rose-700">{workflow.last_error_code || "—"}</td><td>{workflow.attempts.length}</td><td>{formatDate(workflow.updated_at)}</td><td><Button size="sm" variant="outline" asChild><Link to={`/incidents/workflow/${workflow.id}`}>Investigate <ArrowUpRight size={14} /></Link></Button></td></tr>)}</tbody></table></div><Pagination page={workflowPage} count={workflows.data?.count ?? 0} pageSize={WORKFLOW_PAGE_SIZE} onPageChange={setWorkflowPage} /></>}
    </Card>
    <div className="mt-5 flex items-start gap-3 rounded-xl border border-violet-100 bg-violet-50/60 p-4"><Bot size={17} className="mt-0.5 shrink-0 text-violet-600" /><p className="text-xs leading-relaxed text-violet-900">Incident analyses use bounded, sanitized evidence. Recommendations are diagnostic only and never change workflow state.</p></div>
  </>;
}
