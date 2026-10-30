import { Activity, AlertTriangle, BarChart3, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, GitBranch, HeartPulse, Inbox, LayoutDashboard, Menu, PanelLeftClose, PanelLeftOpen, Settings2, ShieldCheck, X, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../app/auth";
import { cn } from "../lib/utils";
import { Button, Badge } from "./ui";

const navItems = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/events", label: "Events", icon: Inbox },
  { to: "/workflows", label: "Workflows", icon: GitBranch },
  { to: "/incidents", label: "AI incidents", icon: AlertTriangle },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/health", label: "System health", icon: HeartPulse },
];

function Sidebar({ close, collapsed = false, onToggle }: { close?: () => void; collapsed?: boolean; onToggle?: () => void }) {
  const { hasToken } = useAuth();
  const compact = collapsed && !close;
  return (
    <aside className={cn("flex h-full shrink-0 flex-col bg-sidebar text-slate-300 transition-[width] duration-200", compact ? "w-[76px]" : "w-[256px]")}>
      <div className={cn("flex h-[76px] items-center gap-3 border-b border-white/[0.08]", compact ? "justify-center px-2" : "px-6")}>
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-500 text-white shadow-lg shadow-blue-900/40"><Activity size={20} strokeWidth={2.5} /></div>
        {!compact && <div><div className="text-[15px] font-bold tracking-tight text-white">EventFlow <span className="text-blue-300">AI</span></div><div className="mt-0.5 text-[9px] font-semibold tracking-wide text-slate-500">Event-Driven Workflow Intelligence</div></div>}
        {onToggle && <button aria-label="Collapse sidebar" title="Collapse sidebar" onClick={onToggle} className="ml-auto rounded-md p-1 text-slate-400 hover:bg-white/10"><PanelLeftClose size={17} /></button>}
        {close && <button aria-label="Close menu" onClick={close} className="ml-auto rounded-md p-1 text-slate-400 hover:bg-white/10 lg:hidden"><X size={19} /></button>}
      </div>
      <div className={cn("pt-6", compact ? "px-2" : "px-4")}>
        {!compact && <div className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-slate-500">Workspace</div>}
        <nav className="space-y-1" aria-label="Main navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={close} title={compact ? label : undefined} className={({ isActive }) => cn("group flex h-10 items-center gap-3 rounded-lg text-[13px] font-medium transition-colors", compact ? "justify-center px-0" : "px-3", isActive ? "bg-blue-500/15 text-blue-200 ring-1 ring-inset ring-blue-400/15" : "text-slate-400 hover:bg-white/[0.06] hover:text-white")}>
            {({ isActive }) => <><Icon size={17} className={cn("shrink-0 transition-colors", isActive ? "text-blue-300" : "text-slate-500 group-hover:text-slate-300")} />{!compact && <span>{label}</span>}</>}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className={cn("my-6 border-t border-white/[0.08]", compact ? "mx-3" : "mx-4")} />
      <div className={compact ? "px-2" : "px-4"}>
        {!compact && <div className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-slate-500">Manage</div>}
        <NavLink to="/settings" onClick={close} title={compact ? "Settings" : undefined} className={({ isActive }) => cn("group flex h-10 items-center gap-3 rounded-lg text-[13px] font-medium transition-colors", compact ? "justify-center px-0" : "px-3", isActive ? "bg-blue-500/15 text-blue-200" : "text-slate-400 hover:bg-white/[0.06] hover:text-white")}><Settings2 size={17} className="shrink-0 text-slate-500 group-hover:text-slate-300" />{!compact && "Settings"}</NavLink>
      </div>
      {!compact && <div className="mt-auto p-4">
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-3.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300"><ShieldCheck size={15} className={hasToken ? "text-emerald-400" : "text-amber-400"} />{hasToken ? "Client token configured" : "Client token needed"}</div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">{hasToken ? "Credential is held in this tab only." : "Add a client token in Settings to access protected APIs."}</p>
          {!hasToken && <NavLink to="/settings" className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-blue-300 hover:text-blue-200">Configure connection <ChevronRight size={13} /></NavLink>}
        </div>
        <div className="mt-4 flex items-center justify-between px-1 text-[10px] text-slate-600"><span>EventFlow Console</span><span>v0.1</span></div>
      </div>}
    </aside>
  );
}

const pageTitles: Record<string, string> = {
  "/overview": "Overview", "/events": "Events", "/workflows": "Workflows", "/incidents": "AI incidents", "/analytics": "Analytics", "/health": "System health", "/settings": "Settings",
};

export function AppLayout() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const title = Object.entries(pageTitles).find(([path]) => location.pathname.startsWith(path))?.[1] ?? "Operations";
  const { hasToken } = useAuth();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="fixed inset-y-0 left-0 z-30 hidden lg:block"><Sidebar collapsed={collapsed} onToggle={() => setCollapsed(true)} /></div>
      {menuOpen && <div className="fixed inset-0 z-40 flex lg:hidden"><button className="absolute inset-0 bg-slate-950/40" aria-label="Close menu" onClick={() => setMenuOpen(false)} /><div className="relative h-full"><Sidebar close={() => setMenuOpen(false)} /></div></div>}
      <div className={cn("min-h-screen transition-[padding] duration-200", collapsed ? "lg:pl-[76px]" : "lg:pl-[256px]")}>
        <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-border/80 bg-white/90 px-5 backdrop-blur-xl sm:px-8">
          <div className="flex items-center gap-3"><Button variant="ghost" size="icon" aria-label="Open navigation" className="lg:hidden" onClick={() => setMenuOpen(true)}><Menu size={19} /></Button><Button variant="ghost" size="icon" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"} className="hidden lg:inline-flex" onClick={() => setCollapsed((value) => !value)}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</Button><div><div className="text-[13px] font-bold text-slate-900">{title}</div><div className="mt-0.5 hidden text-[11px] text-slate-500 sm:block">Monitor and manage event-driven operations</div></div></div>
          <div className="flex items-center gap-3"><div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-500 lg:flex"><span className={cn("h-1.5 w-1.5 rounded-full", hasToken ? "bg-blue-500" : "bg-slate-400")} />{hasToken ? "Client token configured" : "Client token missing"}</div><NavLink to="/settings" aria-label="Open settings" className="grid h-9 w-9 place-items-center rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200"><Settings2 size={17} /></NavLink><div className="hidden h-8 w-px bg-slate-200 sm:block" /><div className="hidden items-center gap-2 sm:flex"><div className="grid h-8 w-8 place-items-center rounded-full bg-blue-600 text-[11px] font-bold text-white">EF</div><div className="text-left"><div className="text-[11px] font-semibold text-slate-800">Operations</div><div className="text-[10px] text-slate-500">Local workspace</div></div><ChevronDown size={14} className="text-slate-400" /></div></div>
        </header>
        <main className="mx-auto max-w-[1440px] px-5 py-7 sm:px-8 sm:py-9"><Outlet /></main>
      </div>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div>{eyebrow && <div className="mb-2 text-[10px] font-bold uppercase tracking-[.16em] text-blue-600">{eyebrow}</div>}<h1 className="text-[25px] font-bold tracking-tight text-slate-950 sm:text-[28px]">{title}</h1>{description && <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-slate-500">{description}</p>}</div>{actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}</div>;
}

export function SectionTitle({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return <div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="text-sm font-bold text-slate-900">{title}</h2>{detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}</div>{action}</div>;
}

export function MetricCard({ title, value, note, icon: Icon, tone = "slate", unavailable = false }: { title: string; value: string; note: string; icon: LucideIcon; tone?: "blue" | "emerald" | "rose" | "amber" | "slate"; unavailable?: boolean }) {
  const tones = { blue: "bg-blue-50 text-blue-600", emerald: "bg-emerald-50 text-emerald-600", rose: "bg-rose-50 text-rose-600", amber: "bg-amber-50 text-amber-600", slate: "bg-slate-100 text-slate-500" };
  return <div className="rounded-xl border border-border bg-card p-4 text-card-foreground shadow-soft"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="truncate text-[11px] font-semibold text-slate-500">{title}</div><div className={"mt-2 text-[25px] font-bold tracking-tight " + (unavailable ? "text-slate-300" : "text-slate-950")}>{value}</div></div><div className={"grid h-9 w-9 shrink-0 place-items-center rounded-lg " + tones[tone]}><Icon size={17} /></div></div><div className="mt-2 min-h-7 text-[9px] leading-relaxed text-slate-400">{note}</div></div>;
}

export function StateBadge({ state }: { state: string }) {
  const variant = ["SUCCEEDED"].includes(state) ? "success" : ["FAILED", "DEAD_LETTERED"].includes(state) ? "danger" : ["PROCESSING", "QUEUED", "RETRYING"].includes(state) ? "info" : ["RETRY_WAIT"].includes(state) ? "warning" : "neutral";
  return <Badge variant={variant}>{state.replaceAll("_", " ")}</Badge>;
}

export function EmptyState({ icon: Icon = CircleHelp, title, description, action }: { icon?: typeof CircleHelp; title: string; description: string; action?: ReactNode }) {
  return <div className="flex flex-col items-center justify-center px-6 py-14 text-center"><div className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-slate-100 text-slate-400"><Icon size={20} /></div><h3 className="text-sm font-bold text-slate-800">{title}</h3><p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">{description}</p>{action && <div className="mt-4">{action}</div>}</div>;
}

export function LoadingState({ label = "Loading data…" }: { label?: string }) {
  return <div role="status" aria-live="polite" className="flex min-h-40 items-center justify-center gap-3 text-sm text-slate-500"><span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />{label}</div>;
}

export function ErrorState({ title = "Couldn’t load this data", description, onRetry }: { title?: string; description: string; onRetry?: () => void }) {
  return <div className="rounded-xl border border-rose-200 bg-rose-50 p-5"><div className="flex gap-3"><AlertTriangle size={18} className="mt-0.5 shrink-0 text-rose-600" /><div className="flex-1"><div className="text-sm font-semibold text-rose-900">{title}</div><p className="mt-1 text-xs leading-relaxed text-rose-800">{description}</p>{onRetry && <Button size="sm" variant="outline" onClick={onRetry} className="mt-3 border-rose-200 bg-white text-rose-800 hover:bg-rose-100">Try again</Button>}</div></div></div>;
}

export function Pagination({ page, count, pageSize, onPageChange }: { page: number; count: number; pageSize: number; onPageChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return <div className="flex flex-col gap-3 border-t border-slate-100 px-4 py-3.5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between"><span>Showing {count === 0 ? 0 : (page - 1) * pageSize + 1}–{Math.min(page * pageSize, count)} of {count}</span><div className="flex items-center gap-1"><Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></Button><span className="px-2">Page <strong className="text-slate-700">{page}</strong> of {pages}</span><Button variant="ghost" size="icon" disabled={page >= pages} onClick={() => onPageChange(page + 1)} aria-label="Next page"><ChevronRight size={16} /></Button></div></div>;
}

