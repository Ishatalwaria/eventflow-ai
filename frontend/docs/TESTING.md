# Frontend Testing and Verification

This document outlines the testing strategy, tooling, execution commands, and coverage scope for the EventFlow AI web operations console.

---

## Test Execution

From the `frontend/` directory, ensure dependencies are installed via `npm ci`, then execute:

```bash
# Run TypeScript compilation check
npm run typecheck

# Run full Vitest test suite once
npm test

# Run tests in interactive watch mode
npm run test:watch

# Verify production build compilation
npm run build
```

---

## Test Framework & Tooling

- **Test Runner:** [Vitest](https://vitest.dev/) (fast, native ESM execution with Vite integration)
- **DOM Environment:** [jsdom](https://github.com/jsdom/jsdom)
- **Component Testing:** [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- **Assertions:** `@testing-library/jest-dom` matchers

---

## Test Suite Coverage

The test suite covers user interactions, API integration, error boundaries, and state management:

| Test File | Focus Area | Description |
|---|---|---|
| `src/test/auth.test.tsx` | Authentication & Access Control | Tests registration form validation, password mismatch rejection, login submission, and session establishment. |
| `src/test/integration.test.tsx` | Full-Console Integration | Exercises cross-page navigation, historical event collection rendering, query filtering, workflow attempt timelines, incident investigation loading, and tenant-scoped overview metrics. |
| `src/test/health.test.tsx` | System Health Monitoring | Verifies public liveness and readiness probe rendering, authenticated `/health/services` rendering, and state retention across route transitions. |
| `src/test/api-client.test.ts` | HTTP Client & Interceptors | Tests Axios request configuration, CSRF header attachment, Bearer token injection, and 401 unauthorized handling. |
| `src/test/api-error.test.ts` | Error Normalization | Validates structured backend API error parsing and user-friendly fallback messaging. |
| `src/test/clipboard.test.ts` | UI Utilities | Verifies safe asynchronous clipboard copy interactions and failure handling. |

---

## Continuous Integration

Frontend tests, TypeScript type checking, production bundle compilation, and high-severity npm security audits (`npm audit --audit-level=high`) are automated as part of the repository's GitHub Actions workflow (`.github/workflows/ci.yml`).
