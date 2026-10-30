# Frontend screenshots

Captured from the local Vite application at tablet viewport size. The browser had no tenant client token configured, so token-gated pages correctly display the API connection state rather than sample records. System Health uses the live liveness and readiness endpoints.

- `overview.jpg` — Overview dashboard and API connection state.
- `events.jpg` — Events page with token-required empty state.
- `workflows.jpg` — Workflow monitoring with token-required empty state.
- `incidents.jpg` — AI incident investigation entry page; history is not exposed by the backend.
- `analytics.jpg` — Analytics capability disclosure and ClickHouse freshness note.
- `system-health.jpg` — Live Django API/PostgreSQL checks and unavailable additional services.
- `settings.jpg` — API base URL and memory-only tenant-token configuration.
