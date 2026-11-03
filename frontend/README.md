# EventFlow AI — Frontend Console

Modern, responsive web operations console for **EventFlow AI**, built with **React 19**, **TypeScript**, **Vite**, **Tailwind CSS**, and **TanStack Query**.

---

## Key Features

- **Dual-Tier Authentication & Access Control:**
  - Secure user onboarding (`/signup`), login (`/login`), and password recovery (`/forgot-password`).
  - Session-based authentication with `HttpOnly` cookies and automatic CSRF protection.
  - In-console API Client key provisioning: create, inspect, copy, and revoke machine ingestion tokens directly in Settings.
- **Real-Time Operational Overview:** High-level system vitals, 7-day terminal volume trends, processing latency percentiles, and outbox delivery metrics.
- **Events Explorer:** Search, filter, inspect payload schemas, and trace workflows across historical ingestion events.
- **Workflow Monitoring & Execution Timelines:** Track stage transitions (`RECEIVED`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `DEAD_LETTERED`), inspect retry counts, and view sanitized execution attempt timelines.
- **AI Incident Investigation:** One-click root-cause analysis for failed workflows. View confirmed facts, confidence-scored hypotheses, and diagnostic recommendations backed by strict evidence citations.
- **Lifecycle Analytics:** Interactive latency percentiles (p50/p95/p99) and stage failure breakdowns. Supports tenant-scoped operational views and high-volume ClickHouse aggregations.
- **System Health Probes:** Live dependency monitoring across PostgreSQL, Kafka, RabbitMQ, ClickHouse, and worker services.

---

## Local Development Setup

### 1. Prerequisites
- **Node.js:** Version 20 LTS or newer
- **npm:** Included with Node.js
- Running EventFlow AI backend (typically via `docker compose up -d` from repository root)

### 2. Install & Start

```bash
# Navigate to frontend directory
cd frontend

# Configure environment variables
cp .env.example .env

# Install locked dependencies
npm ci

# Start the Vite development server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Configuration (`frontend/.env`)

| Variable | Default Value | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Target origin of the EventFlow AI backend API. |

In development mode, Vite automatically proxies `/api` and `/health` requests to `VITE_API_BASE_URL` to ensure same-origin cookie delivery and prevent CORS issues. In production deployments, configure your gateway or reverse proxy to route `/api` to the backend.

---

## Available Scripts

From the `frontend/` directory:

```bash
# Start development server with hot-module replacement
npm run dev

# Run TypeScript compiler checks
npm run typecheck

# Run unit and integration tests with Vitest and React Testing Library
npm test

# Run tests in watch mode
npm run test:watch

# Compile optimized production bundle into dist/
npm run build

# Preview production build locally
npm run preview
```

---

## Directory Structure

```text
frontend/
├── docs/
│   ├── API_INTEGRATION_MAP.md   # Endpoint contracts and payload schemas
│   ├── TESTING.md               # Testing methodology and coverage scope
│   └── screenshots/             # Interface screenshots and previews
├── src/
│   ├── api/                     # Axios instance, typed API clients, error normalization
│   ├── app/                     # Providers (Auth, TanStack Query, Theme), Router
│   ├── components/              # Shared UI design system, layout shells, dialogs, badges
│   ├── features/                # Domain feature modules:
│   │   ├── auth/                # Login, Signup, Forgot Password views
│   │   ├── overview/            # System vitals and KPI dashboards
│   │   ├── events/              # Event ingestion form, list, and detail views
│   │   ├── workflows/           # Workflow monitoring and execution timeline
│   │   ├── incidents/           # AI incident investigation workspace
│   │   ├── analytics/           # Tenant and ClickHouse lifecycle charts
│   │   ├── health/              # Service health probes and worker telemetry
│   │   └── settings/            # API client management and user preferences
│   ├── lib/                     # Formatting utilities, type definitions, validation schemas
│   ├── styles.css               # Tailwind CSS and design tokens
│   ├── test/                    # Integration and component unit tests
│   ├── App.tsx                  # Root application router and route definitions
│   └── main.tsx                 # Application entrypoint
├── package.json
├── tsconfig.json
└── vite.config.ts
```
