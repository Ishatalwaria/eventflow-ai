# Frontend testing and verification

Run these from `frontend/` after installing the locked dependencies with `npm ci`:

```powershell
npm run typecheck
npm test
npm run build
```

The Vitest and Testing Library suite covers application navigation, event list rendering, event submission, workflow execution details, incident analysis sections, the explicit analytics-unavailable state, shared loading and empty states, API error normalization, 401 token clearing, and endpoint-backed health rendering.

## Live backend scope

The browser preview confirmed Django liveness and PostgreSQL readiness through `/health/live` and `/health/ready`. The frontend does not call the protected `/metrics` endpoint. Tenant-authenticated event submission/retrieval, workflow retrieval, and incident analysis require a valid backend-issued `CLIENT_UUID.SECRET` token, and were not exercised in this verification session. The tests cover UI/API-client behavior, not that external credentialed flow.

## Tooling status

There is no ESLint configuration or lint script in this frontend, so ESLint is not configured. `npm run build` includes the TypeScript project checks. Tests use Vitest, jsdom, and React Testing Library.

## Unsupported backend capabilities shown in the UI

- Browser-queryable ClickHouse analytics and data-freshness timestamps.
- Event list/search API and incident history API.
- Health endpoints for Kafka, RabbitMQ, ClickHouse, workers, and the LLM provider.
- Browser-safe API/worker/queue/retry/dead-letter/LLM metrics. `/metrics` requires a separate `X-Metrics-Token`.
- A user-authenticated production session; the tenant client credential is held in page memory and is not an end-user identity mechanism.

These are displayed as unavailable or described in the interface; no metrics or incident explanations are fabricated.
