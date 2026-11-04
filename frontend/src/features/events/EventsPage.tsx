import { useMutation } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Clipboard, FileJson2, RefreshCw, Search, Send, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiErrorMessage } from "../../api/client";
import { useCreateEvent, useCreateEventBatch, useEvents } from "../../api/hooks";
import { eventsService } from "../../api/services/events";
import type { EventDetail, EventEnvelope } from "../../api/types";
import { useAuth } from "../../app/auth";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState, PageHeader, Pagination, StateBadge } from "../../components/layout";
import { Button, Card, DataTable, Input, Label, Select, Textarea } from "../../components/ui";
import { compactId, formatDate } from "../../lib/utils";
import { copyToClipboard } from "../../lib/clipboard";

const orderPayloadSchema = z.object({
  order_id: z.string().min(1).max(128),
  currency: z.string().regex(/^[A-Z]{3}$/),
  total_minor_units: z.number().int().min(0),
  payment_method_token: z.string().min(1).max(128).optional(),
  items: z.array(z.object({ sku: z.string().min(1).max(100), quantity: z.number().int().min(1) })).min(1).max(100),
});

const replenishmentPayloadSchema = z.object({
  sku: z.string().min(1).max(100),
  quantity: z.number().int().min(1),
  approval_token: z.string().min(1).max(128).optional(),
});

const paymentRecoveryPayloadSchema = z.object({
  source_workflow_id: z.string().uuid(),
  payment_method_token: z.string().min(1).max(128).optional(),
});

const eventSchema = z.object({
  event_type: z.enum([
    "order.created",
    "inventory.replenishment.requested",
    "payment.recovery.requested",
  ]),
  schema_version: z.literal(1),
  source: z.string().min(1).max(100).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$/),
  idempotency_key: z.string().min(1).max(255).regex(/^[\x21-\x7E]+$/),
  occurred_at: z.string().datetime({ offset: true }),
  correlation_id: z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/),
  payload: z.any(),
});
const eventFormSchema = eventSchema.extend({ payload: z.any() });
const batchSchema = z.array(eventSchema).min(1).max(50);
type EventForm = z.infer<typeof eventSchema>;

function blankEvent(): EventForm {
  const id = crypto.randomUUID();
  return {
    event_type: "order.created",
    schema_version: 1,
    source: "checkout-web",
    idempotency_key: id,
    occurred_at: new Date().toISOString(),
    correlation_id: id,
    payload: {
      order_id: "ORD-" + id.slice(0, 8).toUpperCase(),
      currency: "INR",
      total_minor_units: 24900,
      payment_method_token: "ok_card",
      items: [{ sku: "ITEM-KEYBOARD", quantity: 1 }],
    },
  };
}

interface ScenarioDefinition {
  label: string;
  eventType: "order.created" | "inventory.replenishment.requested" | "payment.recovery.requested";
  payload: Record<string, unknown>;
}

const SCENARIOS: ScenarioDefinition[] = [
  {
    label: "Order: Happy path",
    eventType: "order.created",
    payload: {
      order_id: "ORD-HAPPY",
      currency: "INR",
      total_minor_units: 24900,
      payment_method_token: "ok_card",
      items: [{ sku: "ITEM-KEYBOARD", quantity: 1 }],
    },
  },
  {
    label: "Order: Payment declined (Compensates)",
    eventType: "order.created",
    payload: {
      order_id: "ORD-DECLINE",
      currency: "INR",
      total_minor_units: 24900,
      payment_method_token: "fail_card",
      items: [{ sku: "ITEM-KEYBOARD", quantity: 1 }],
    },
  },
  {
    label: "Order: Payment timeout (Retries)",
    eventType: "order.created",
    payload: {
      order_id: "ORD-TIMEOUT",
      currency: "INR",
      total_minor_units: 24900,
      payment_method_token: "timeout_card",
      items: [{ sku: "ITEM-KEYBOARD", quantity: 1 }],
    },
  },
  {
    label: "Order: Out of stock (Rejection)",
    eventType: "order.created",
    payload: {
      order_id: "ORD-OOS",
      currency: "INR",
      total_minor_units: 7900,
      payment_method_token: "ok_card",
      items: [{ sku: "OOS-MOUSE", quantity: 1 }],
    },
  },
  {
    label: "Replenish: Stock approval",
    eventType: "inventory.replenishment.requested",
    payload: {
      sku: "ITEM-KEYBOARD",
      quantity: 50,
      approval_token: "approve",
    },
  },
  {
    label: "Replenish: Rejected request",
    eventType: "inventory.replenishment.requested",
    payload: {
      sku: "ITEM-KEYBOARD",
      quantity: 100,
      approval_token: "reject_over_quota",
    },
  },
  {
    label: "Payment Recovery: Retry authorization",
    eventType: "payment.recovery.requested",
    payload: {
      source_workflow_id: "00000000-0000-0000-0000-000000000000",
      payment_method_token: "ok_card",
    },
  },
];

export function EventsPage() {
  const { hasToken, token } = useAuth();
  const [tab, setTab] = useState<"single" | "batch">("single");
  const [lookupId, setLookupId] = useState("");
  const [eventDetail, setEventDetail] = useState<EventDetail | null>(null);
  const [payloadText, setPayloadText] = useState(() => JSON.stringify(blankEvent().payload, null, 2));
  const [payloadError, setPayloadError] = useState("");
  const singleTokenRef = useRef(token);
  const batchTokenRef = useRef(token);
  const form = useForm<EventForm>({ resolver: zodResolver(eventFormSchema), defaultValues: blankEvent() });
  const single = useCreateEvent();
  useEffect(() => {
    if (!single.data || singleTokenRef.current !== token) return;
    toast.success(single.data.duplicate ? "Duplicate accepted. Existing event returned." : "Event accepted and workflow created.");
  }, [single.data, token]);
  const [batchText, setBatchText] = useState("[]");
  const batch = useCreateEventBatch();
  useEffect(() => {
    if (!batch.data || batchTokenRef.current !== token) return;
    toast.success("Batch accepted: " + batch.data.results.length + " result(s).");
  }, [batch.data, token]);
  const lookup = useMutation({ mutationFn: (id: string) => eventsService.get(id), onSuccess: (data) => { setEventDetail(data); toast.success("Event loaded."); }, onError: () => setEventDetail(null) });
  const onSingle = form.handleSubmit((data) => {
    let parsed: unknown;
    try { parsed = JSON.parse(payloadText); }
    catch { setPayloadError("Enter valid JSON for the event payload."); return; }
    const currentType = data.event_type;
    let schemaToValidate = orderPayloadSchema;
    if (currentType === "inventory.replenishment.requested") {
      schemaToValidate = replenishmentPayloadSchema as any;
    } else if (currentType === "payment.recovery.requested") {
      schemaToValidate = paymentRecoveryPayloadSchema as any;
    }
    const payload = schemaToValidate.safeParse(parsed);
    if (!payload.success) {
      setPayloadError(payload.error.issues[0]?.message ?? `Payload does not match the ${currentType} schema.`);
      return;
    }
    setPayloadError(""); singleTokenRef.current = token; single.mutate({ ...data, payload: payload.data });
  });
  const resetForm = () => { const next = blankEvent(); form.reset(next); setPayloadText(JSON.stringify(next.payload, null, 2)); setPayloadError(""); single.reset(); };
  const onBatch = () => {
    try {
      const parsed: unknown = JSON.parse(batchText);
      const result = batchSchema.safeParse(parsed);
      if (!result.success) { toast.error(result.error.issues[0]?.message ?? "Batch does not match the event schema."); return; }
      batchTokenRef.current = token;
      batch.mutate(result.data as EventEnvelope[]);
    } catch { toast.error("Enter a valid JSON array of event envelopes."); }
  };
  const fieldError = (name: keyof EventForm) => form.formState.errors[name]?.message?.toString();

  return <>
    <PageHeader eyebrow="Event ingestion" title="Events" description="Submit order fulfillment, replenishment, and recovery events." />
    {hasToken && <EventCollectionTable enabled={hasToken} />}
    {!hasToken ? <Card><EmptyState icon={Send} title="API connection required" description="Connect a client token in Settings before submitting or inspecting events." /></Card> : <div className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
      <Card className="overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><h2 className="text-sm font-bold text-slate-900">Event intake</h2><p className="mt-1 text-xs text-slate-500">Select demonstration scenario or enter custom JSON.</p></div><div className="flex rounded-lg bg-slate-100 p-1"><button className={"rounded-md px-3 py-1.5 text-xs font-semibold " + (tab === "single" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500")} onClick={() => setTab("single")}>Single event</button><button className={"rounded-md px-3 py-1.5 text-xs font-semibold " + (tab === "batch" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500")} onClick={() => setTab("batch")}>Batch JSON</button></div></div>
        {tab === "single" ? <form onSubmit={onSingle} className="space-y-5 p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Source" error={fieldError("source")}><Input {...form.register("source")} placeholder="checkout-web" /></Field>
            <Field label="Event type" error={fieldError("event_type")}>
              <Select
                {...form.register("event_type")}
                onChange={(e) => {
                  const val = e.target.value as EventForm["event_type"];
                  form.setValue("event_type", val);
                  if (val === "order.created") {
                    setPayloadText(JSON.stringify(SCENARIOS[0].payload, null, 2));
                  } else if (val === "inventory.replenishment.requested") {
                    setPayloadText(JSON.stringify(SCENARIOS[4].payload, null, 2));
                  } else if (val === "payment.recovery.requested") {
                    setPayloadText(JSON.stringify(SCENARIOS[6].payload, null, 2));
                  }
                  setPayloadError("");
                }}
              >
                <option value="order.created">order.created (Order Fulfillment Saga)</option>
                <option value="inventory.replenishment.requested">inventory.replenishment.requested (Replenishment)</option>
                <option value="payment.recovery.requested">payment.recovery.requested (Payment Recovery Saga)</option>
              </Select>
            </Field>
            <Field label="Idempotency key" error={fieldError("idempotency_key")}><Input {...form.register("idempotency_key")} /></Field>
            <Field label="Correlation ID" error={fieldError("correlation_id")}><Input {...form.register("correlation_id")} /></Field>
            <Field label="Occurred at (ISO 8601 with timezone)" error={fieldError("occurred_at")}><Input {...form.register("occurred_at")} placeholder="2026-10-30T10:00:00Z" /></Field>
          </div>
          <div className="space-y-1.5">
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Preset Scenarios</div>
            <div className="flex flex-wrap gap-2">
              {SCENARIOS.map((scenario) => (
                <Button
                  key={scenario.label}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    form.setValue("event_type", scenario.eventType);
                    setPayloadText(JSON.stringify(scenario.payload, null, 2));
                    setPayloadError("");
                  }}
                >
                  {scenario.label}
                </Button>
              ))}
            </div>
          </div>
          <Field label="Payload JSON" error={payloadError}><Textarea id="event-payload" value={payloadText} onChange={(event) => { setPayloadText(event.target.value); setPayloadError(""); }} className="min-h-56 font-mono text-xs leading-relaxed" spellCheck={false} aria-describedby="payload-contract" /></Field>
          <p id="payload-contract" className="-mt-3 text-[11px] text-slate-400">Tokens ok_card, fail_card, and timeout_card drive the payment simulator. Approval tokens approve and reject drive replenishment.</p>
          {single.isError && <ErrorState title="Event submission failed" description={apiErrorMessage(single.error)} />}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"><span className="text-[11px] text-slate-400">Submitting creates the event, initial workflow, and outbox record atomically.</span><div className="flex gap-2"><Button type="button" variant="outline" onClick={resetForm} disabled={single.isPending}>Cancel</Button><Button type="submit" disabled={single.isPending}><Send size={15} />{single.isPending ? "Submitting…" : "Submit event"}</Button></div></div>
        </form> : <div className="space-y-4 p-5 sm:p-6"><div className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs leading-relaxed text-blue-800">Submit a JSON array of 1–50 event envelopes. The full batch is accepted or rolled back as one transaction.</div><Label htmlFor="batch-file">Upload JSON array (optional)</Label><Input id="batch-file" type="file" accept="application/json,.json" onChange={async (event) => { const file = event.target.files?.[0]; if (file) { setBatchText(await file.text()); toast.success("Batch JSON loaded."); } }} /><Label htmlFor="batch-json">Event envelopes (JSON)</Label><Textarea id="batch-json" value={batchText} onChange={(event) => setBatchText(event.target.value)} className="min-h-[320px] font-mono text-xs leading-relaxed" spellCheck={false} /><div className="flex items-center justify-between gap-3">{batch.isError ? <span className="text-xs text-rose-700">{apiErrorMessage(batch.error)}</span> : <span className="text-[11px] text-slate-400">Batch limit: 50 events · request limit: 256 KiB</span>}<Button onClick={onBatch} disabled={batch.isPending}><Upload size={15} />{batch.isPending ? "Submitting…" : "Submit batch"}</Button></div>{batch.data && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">Batch accepted. {batch.data.results.length} results returned.</div>}</div>}
      </Card>
      <div className="space-y-5">
        <Card className="overflow-hidden"><div className="border-b border-slate-100 p-5"><h2 className="text-sm font-bold text-slate-900">Inspect an event</h2><p className="mt-1 text-xs text-slate-500">Load a known event UUID from the backend.</p></div><div className="space-y-3 p-5"><div className="flex gap-2"><Input aria-label="Event UUID" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder="Event UUID" /><Button aria-label="Search event" disabled={!lookupId.trim() || lookup.isPending} onClick={() => lookup.mutate(lookupId.trim())}><Search size={16} /></Button></div>{lookup.isPending && <LoadingState label="Loading event…" />}{lookup.isError && <div className="text-xs text-rose-700">{apiErrorMessage(lookup.error)}</div>}{eventDetail && <EventDetails detail={eventDetail} />}</div></Card>
      </div>
    </div>}
  </>;
}

function EventCollectionTable({ enabled }: { enabled: boolean }) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [eventType, setEventType] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 8;
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [search]);
  const events = useEvents({
    page,
    page_size: pageSize,
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(eventType !== "all" ? { event_type: eventType } : {}),
    ...(fromDate ? { date_from: fromDate } : {}),
    ...(toDate ? { date_to: toDate } : {}),
  }, enabled);
  const records = events.data?.results ?? [];
  return <Card className="mb-5 overflow-hidden">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4"><div><h2 className="text-sm font-bold text-slate-900">Event history</h2><p className="mt-1 text-xs text-slate-500">Historical event records from the authenticated API.</p></div><Button size="sm" variant="outline" onClick={() => void events.refetch()} disabled={events.isFetching}><RefreshCw size={14} />Refresh</Button></div>
    <div className="grid gap-2 border-b border-slate-100 p-4 sm:grid-cols-2 xl:grid-cols-4"><Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search ID, source, key…" aria-label="Search events" /><Select value={eventType} onChange={(event) => { setEventType(event.target.value); setPage(1); }} aria-label="Filter by event type"><option value="all">All event types</option><option value="order.created">order.created</option></Select><Input type="date" value={fromDate} onChange={(event) => { setFromDate(event.target.value); setPage(1); }} aria-label="Received from date" /><Input type="date" value={toDate} onChange={(event) => { setToDate(event.target.value); setPage(1); }} aria-label="Received through date" /></div>
    {events.isLoading ? <div className="p-6"><LoadingState label="Loading events…" /></div> : events.isError ? <div className="p-5"><ErrorState title="Event history unavailable" description={apiErrorMessage(events.error)} onRetry={() => void events.refetch()} /></div> : !records.length ? <EmptyState icon={FileJson2} title={debouncedSearch || eventType !== "all" || fromDate || toDate ? "No matching events" : "No events yet"} description={debouncedSearch || eventType !== "all" || fromDate || toDate ? "Adjust the filters or search term." : "Accepted events will appear here after they are submitted."} /> : <DataTable rows={records} rowKey={(event) => event.id} columns={[
      { key: "id", header: "Event ID", cell: (event) => <Link className="font-mono text-blue-700 hover:underline" to={`/events/${event.id}`}>{compactId(event.id, 12)}</Link> },
      { key: "type", header: "Event type", cell: (event) => event.event_type, className: "font-medium text-slate-800" },
      { key: "source", header: "Source", cell: (event) => event.source },
      { key: "schema", header: "Schema", cell: (event) => `v${event.schema_version}` },
      { key: "received", header: "Received", cell: (event) => formatDate(event.received_at) },
      { key: "idempotency", header: "Idempotency key", cell: (event) => event.idempotency_key, className: "max-w-40 truncate" },
      { key: "correlation", header: "Correlation ID", cell: (event) => event.correlation_id, className: "max-w-40 truncate" },
      { key: "status", header: "Status", cell: (event) => <StateBadge state={event.workflow.state} /> },
      { key: "actions", header: "", cell: (event) => <Link to={`/events/${event.id}`} className="font-semibold text-blue-700 hover:underline">Details</Link> },
    ]} />}
    {!!events.data?.count && <Pagination page={page} count={events.data.count} pageSize={pageSize} onPageChange={setPage} />}
  </Card>;
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><label className="block space-y-1.5"><span className="text-sm font-semibold text-slate-700">{label}</span>{children}</label>{error && <p className="text-[11px] text-rose-600">{error}</p>}</div>;
}

function EventDetails({ detail }: { detail: EventDetail }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { if (await copyToClipboard(detail.id, "Event ID copied.")) { setCopied(true); window.setTimeout(() => setCopied(false), 1200); } };
  return <div className="rounded-xl border border-slate-100 bg-slate-50 p-4"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="text-sm font-bold text-slate-900">{detail.event_type}</div><div className="mt-1 break-all font-mono text-[10px] text-slate-500">{detail.id}</div></div><Button size="icon" variant="ghost" aria-label="Copy event ID" onClick={copy}><Clipboard size={15} /></Button></div><div className="mt-3 flex items-center justify-between"><StateBadge state={detail.workflow.state} /><span className="text-[10px] text-slate-400">Received {formatDate(detail.received_at)}</span></div><dl className="mt-4 space-y-2 text-xs"><Row label="Source" value={detail.source} /><Row label="Correlation" value={detail.correlation_id} /><Row label="Workflow" value={compactId(detail.workflow.id, 28)} /></dl><pre className="mt-4 max-h-48 overflow-auto rounded-lg bg-slate-900 p-3 text-[10px] leading-relaxed text-slate-200">{JSON.stringify(detail.payload, null, 2)}</pre>{copied && <span className="sr-only">Copied</span>}</div>;
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-slate-400">{label}</dt><dd className="max-w-[65%] truncate text-right font-medium text-slate-700">{value}</dd></div>;
}
