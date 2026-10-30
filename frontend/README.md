# EventFlow AI Frontend

React + TypeScript operations console for the existing EventFlow Django API. Backend code is not modified by this frontend.

## Run the backend and frontend together

From the repository root, start the services defined by the existing Compose configuration:

```powershell
docker compose up --build -d
```

Then start the frontend in a second terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open `http://localhost:5173`. `VITE_API_BASE_URL=http://localhost:8000` configures the backend target. In development, Vite proxies API and health requests to this URL so browser calls stay same-origin. For production, set the deployed API origin; configure CORS at the gateway if origins differ. Add a client token in Settings using the exact `CLIENT_UUID.SECRET` value issued by the backend. It is held in JavaScript memory only and is cleared on reload.

The client bearer token is a credential, not an end-user session. Memory-only storage limits persistence but does not prevent the browser owner or page scripts from accessing it. Use a server-side backend-for-frontend for production user-facing deployments; never place Django, database, Kafka, RabbitMQ, or LLM credentials in browser code.

## Checks

```powershell
npm run typecheck
npm test
npm run build
```

Test coverage and known gaps are documented in [`docs/TESTING.md`](docs/TESTING.md). Page captures are listed in [`docs/screenshots/README.md`](docs/screenshots/README.md).

## Actual backend coverage

See [`docs/API_INTEGRATION_MAP.md`](docs/API_INTEGRATION_MAP.md). Workflow list/detail, event create/batch/detail, incident-summary creation, liveness/readiness, and OpenAPI docs are integrated. Workflow state groups map to the backend's actual values, and execution timelines use recorded attempt rows. The incident workspace analyzes an eligible failed workflow on request. The backend does not expose event listing, incident history, analytics queries, standalone processing logs, or per-service health endpoints. Those areas are labeled in the UI instead of showing invented data.

Analytics and the metrics requested on the System Health page remain unavailable to browser clients: ClickHouse reporting is management-command-only, while `/metrics` requires a separate metrics token. API and database health are checked through the public liveness and readiness endpoints. No event/workflow/incident success flow was claimed from a live browser session without a tenant client token.
