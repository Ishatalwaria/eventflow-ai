# 03 — Frontend requirement gap analysis

## Phase 0 — API contract mapping

**Implemented and mostly aligned.** frontend/docs/API_INTEGRATION_MAP.md maps event create/batch/list/detail, workflow list/detail, incident create/list/detail, lifecycle analytics, health live/ready, schema/docs and protected metrics. It documents Bearer auth, the explicit system-wide analytics capability, payload/response shapes, filters, pagination, request limits and unsupported capabilities. Live OpenAPI and auth paths were verified.

**Contract documentation gap:** operation inspection found GET /api/v1/workflows schema exposes page/page_size but omits the state filter implemented by the query serializer/view. API operations enumerate successful responses only, omitting common API error statuses/envelopes. Schema-driven clients could miss behavior.

## Phase 1 — Foundation and design system

**Implemented.** Vite/React/TypeScript, Tailwind, Radix-based primitives, React Router, responsive shell, sidebar/drawer, top bar, shared headers/cards/tables/badges/dialogs/toasts and state components exist. Required navigation is present. Styles include reduced-motion and responsive table scrolling. A fresh screenshot audit was not completed as part of this engineering audit.

## Phase 2 — API integration

**Implemented and verified.** Shared Axios uses VITE_API_BASE_URL, 12-second timeout, interceptors, request IDs and 401 token clearing. Service modules and query hooks cover actual browser endpoints. Workflow details poll every five seconds while nonterminal; health polls every 30 seconds. Error mapping covers auth, forbidden, not found, rate limit, server/upstream, payload-size, network and timeout failures. Authenticated live event, workflow, incident and analytics requests were exercised; frontend tests use service fixtures rather than live browser sessions.

Token stays in JS memory/React context and clears on reload/401. This is not a production user session and remains visible to browser owner/page scripts. No valid-token API request was made in audit.

## Phase 3 — Overview

**Partial, transparent about API gaps.** Success/failure/pending workflow state counts and donut use actual paginated workflow API values. Counts use seven parallel per-state requests plus total/recent calls, creating avoidable request volume and a slightly non-atomic snapshot during concurrent changes. Total events, processed events, latency, activity series and recent event feed are unavailable and not fabricated. Outbox backlog unavailable to browser.

Workflow “attempt time” is a sum of recorded attempt durations, not necessarily end-to-end latency. Preserve that distinction. There is no backend aggregate snapshot/freshness endpoint.

## Phase 4 — Events

**Updated 2026-10-31.** The events page uses the tenant-scoped backend collection for historical rows, server-side search/type/date filters and pagination; it no longer builds the table from sessionStorage receipt IDs. Single/batch submission, validation, detail, and workflow navigation remain. The incidents page lists persisted analyses and reopens their bounded evidence by ID while retaining discovery of failed workflows eligible for new analysis. Live authenticated event and incident journeys are verified; collection responses omit payload/evidence.

## Phase 5 — Workflows

**Implemented against available contract; live workflow data verified.** List, state groups, search, pagination, details, recorded-attempt timeline, errors and related-event links exist. No stage is shown as successful without an attempt record. Standalone logs are disclosed as unavailable. Five-second polling stops at terminal states. Unsupported cancel/retry/replay actions were not found.

## Phase 6 — AI Incident Assistant

**Updated 2026-10-31.** The incidents page separates persisted incident summaries from eligible failed/dead-lettered workflows. Saved summaries can be searched, filtered, paginated, opened by ID, and reloaded with their evidence. Live local-provider analysis and tenant isolation are verified; external provider behavior remains untested.

## Phase 7 — Analytics and System Health

**Analytics is API-backed; health remains partial.** Analytics charts call the bounded ClickHouse lifecycle endpoint, show its actual freshness/lag and eventual consistency, and provide date filters. The endpoint is limited to clients with an explicit analytics capability because its aggregates are system-wide. Health page polls actual liveness/readiness; only API and PostgreSQL are reported as checks. Other services and protected metrics are unavailable.

## Phase 8 — Settings/security/final integration

**Partial.** Settings shows API URL, environment mode, live/readiness, token configuration; avoids displaying secret values; token held only in memory; BFF limitation documented. React renders content as text/JSON; source scan found no dangerouslySetInnerHTML, innerHTML, eval or localStorage. Current frontend tests cover navigation, event list/submission, workflow detail, incident analysis, analytics charts/access denial, common loading/empty, API errors/401 and health.

ESLint is not configured. GitHub Actions does not run frontend typecheck/tests/build/dependency audit. No real authenticated browser/backend flow has been verified.

## Final UI/UX audit

| Concern | Finding |
|---|---|
| Consistency | Shared components and palette exist, though pages still include one-off utility compositions and some very small secondary text. Fresh visual inspection not completed. |
| Navigation | Required routes exist; event links now target detail routes. No test covers all direct/nested deep links. |
| Tables | Shared text is more readable and horizontal scrolling is contained; dense tables still require horizontal scrolling on narrow screens. |
| Charts | Workflow distribution and analytics visualizations are backed by actual APIs; analytics explicitly labels ClickHouse results as eventually consistent and displays freshness. |
| Status | Shared StateBadge maps terminal, processing, retry-wait and retrying outcomes. Unknown states are neutral. |
| Responsive/accessibility | Drawer/table scroll and focus styles exist; no automated viewport overflow or axe audit. |
| Loading/errors | Shared and page-specific states exist; tests cover examples, not a complete route/state matrix. |
| Feedback | Toasts used for key actions. Analytics nonfunctional refresh removed. Some clipboard handlers in Events/WorkflowDetail do not catch rejected clipboard access, unlike EventDetail/Incident. |

## Unsupported frontend capabilities

- Detailed per-service health and metrics beyond the available API/PostgreSQL readiness checks.
- Browser-queryable analytics/time-range endpoint.
- Browser-safe protected metrics.
- Kafka/Rabbit/ClickHouse/worker/LLM health endpoints.
- Production user auth/session boundary for browser client.
