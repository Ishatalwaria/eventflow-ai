import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout, EmptyState } from "./components/layout";
import { Card } from "./components/ui";

const LoginPage = lazy(() => import("./features/auth/LoginPage").then((m) => ({ default: m.LoginPage })));
const SignupPage = lazy(() => import("./features/auth/SignupPage").then((m) => ({ default: m.SignupPage })));
const ForgotPasswordPage = lazy(() => import("./features/auth/ForgotPasswordPage").then((m) => ({ default: m.ForgotPasswordPage })));

const OverviewPage = lazy(() => import("./features/overview/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const EventsPage = lazy(() => import("./features/events/EventsPage").then((module) => ({ default: module.EventsPage })));
const EventDetailPage = lazy(() => import("./features/events/EventDetailPage").then((module) => ({ default: module.EventDetailPage })));
const WorkflowsPage = lazy(() => import("./features/workflows/WorkflowsPage").then((module) => ({ default: module.WorkflowsPage })));
const WorkflowDetailPage = lazy(() => import("./features/workflows/WorkflowDetailPage").then((module) => ({ default: module.WorkflowDetailPage })));
const IncidentsPage = lazy(() => import("./features/incidents/IncidentsPage").then((module) => ({ default: module.IncidentsPage })));
const IncidentInvestigationPage = lazy(() => import("./features/incidents/IncidentInvestigationPage").then((module) => ({ default: module.IncidentInvestigationPage })));
const AnalyticsPage = lazy(() => import("./features/analytics/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));
const HealthPage = lazy(() => import("./features/health/HealthPage").then((module) => ({ default: module.HealthPage })));
const SettingsPage = lazy(() => import("./features/settings/SettingsPage").then((module) => ({ default: module.SettingsPage })));

function NotFound() {
  return (
    <Card>
      <EmptyState title="Page not found" description="This page is not part of the EventFlow operations console." />
    </Card>
  );
}

export default function App() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <p className="text-xs font-medium tracking-wide">Loading EventFlow AI…</p>
          </div>
        </div>
      }
    >
      <Routes>
        {/* Public Authentication Routes */}
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route path="forgot-password" element={<ForgotPasswordPage />} />

        {/* Console Routes */}
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="events" element={<EventsPage />} />
          <Route path="events/:eventId" element={<EventDetailPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/id/:incidentId" element={<IncidentInvestigationPage />} />
          <Route path="incidents/workflow/:workflowId" element={<IncidentInvestigationPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="health" element={<HealthPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
