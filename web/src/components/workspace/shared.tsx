import React, { useCallback, useEffect, useState } from 'react';
import { nexusJson } from '../../api';

/* ────────────────────────────────────────────────────────────────────────────
 * NEXUS OS light workspace — shared design system & live-fetch plumbing.
 * Every view in the suite speaks this language: off-white canvas, white
 * rounded-3xl cards, slate hierarchy, one accent per surface, live data.
 * ──────────────────────────────────────────────────────────────────────────── */

export type WorkspaceRoute =
  | 'HOME'
  | 'GRAPH'
  | 'RESEARCH'
  | 'WORKFLOW'
  | 'ARCHITECTURE'
  | 'ANALYTICS'
  | 'AGENTS';

export interface RouteAccent {
  /** 500-level hex used for dots, charts and SVG strokes */
  hex: string;
  /** tailwind text class */
  text: string;
  /** soft background class */
  soft: string;
  /** border class */
  border: string;
}

export const ROUTE_META: Record<WorkspaceRoute, { eyebrow: string; title: string; subtitle: string; accent: RouteAccent }> = {
  HOME: {
    eyebrow: 'Workspace',
    title: '',
    subtitle: '',
    accent: { hex: '#0EA5E9', text: 'text-cyan-600', soft: 'bg-cyan-50', border: 'border-cyan-200' },
  },
  GRAPH: {
    eyebrow: 'Living Knowledge Graph',
    title: 'Second Brain Constellation',
    subtitle: 'Every concept, tool and suite the cortex knows — laid out as a live force-directed constellation. Drag nodes, filter clusters, and send any node straight into deep research.',
    accent: { hex: '#06B6D4', text: 'text-cyan-600', soft: 'bg-cyan-50', border: 'border-cyan-200' },
  },
  RESEARCH: {
    eyebrow: 'Autonomous Deep Research',
    title: 'Research Lab',
    subtitle: 'Multi-hop autonomous research: decompose, search, browse, corroborate, synthesise — then ingest the findings into the second brain as live graph nodes.',
    accent: { hex: '#8B5CF6', text: 'text-violet-600', soft: 'bg-violet-50', border: 'border-violet-200' },
  },
  WORKFLOW: {
    eyebrow: 'Workflow Canvas',
    title: 'Orchestration DAGs',
    subtitle: 'Visual step orchestrators with live execution telemetry. Trigger a workflow and watch each step hand off to the next through the agent mesh.',
    accent: { hex: '#10B981', text: 'text-emerald-600', soft: 'bg-emerald-50', border: 'border-emerald-200' },
  },
  ARCHITECTURE: {
    eyebrow: 'Hexagonal Architecture',
    title: 'Ports & Adapters',
    subtitle: 'Strict domain isolation, live from the running API: the domain hexagon, the application use-case ring, and the infrastructure adapters registered on this very server.',
    accent: { hex: '#F59E0B', text: 'text-amber-600', soft: 'bg-amber-50', border: 'border-amber-200' },
  },
  ANALYTICS: {
    eyebrow: 'Analytics Dashboard',
    title: 'System Intelligence',
    subtitle: 'KPI telemetry, request distribution, and graph composition — sampled live from the running cortex.',
    accent: { hex: '#3B82F6', text: 'text-blue-600', soft: 'bg-blue-50', border: 'border-blue-200' },
  },
  AGENTS: {
    eyebrow: 'Agent Orchestration',
    title: 'The Swarm',
    subtitle: 'The enterprise agent roster — live registrations plus the built-in standby swarm. Commission new agents and watch the inter-agent message bus flow.',
    accent: { hex: '#6366F1', text: 'text-indigo-600', soft: 'bg-indigo-50', border: 'border-indigo-200' },
  },
};

export const GRAPH_GROUP_COLORS: Record<string, string> = {
  Router: '#0F172A',
  Suites: '#6366F1',
  Tools: '#F59E0B',
  Concepts: '#0EA5E9',
  Worlds: '#10B981',
  Skills: '#8B5CF6',
  Tasks: '#F97316',
  Notes: '#14B8A6',
  Files: '#94A3B8',
  Memory: '#EC4899',
};

export function graphGroupColor(group?: string): string {
  return GRAPH_GROUP_COLORS[group ?? ''] ?? '#64748B';
}

export function formatUptime(seconds: number): string {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/* ── Live fetch hook — polling with graceful offline state ────────────────── */

export function useLiveFetch<T>(path: string | null, intervalMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    (async () => {
      try {
        const payload = await nexusJson<T>(path);
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? 'Backend unreachable');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  useEffect(() => {
    if (!path || !intervalMs) return;
    const id = window.setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => window.clearInterval(id);
  }, [path, intervalMs]);

  return { data, error, loading: data === null && error === null, reload };
}

/* ── Shared chrome ────────────────────────────────────────────────────────── */

interface PageHeaderProps {
  route: Exclude<WorkspaceRoute, 'HOME'>;
  right?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ route, right }) => {
  const meta = ROUTE_META[route];
  return (
    <header className="flex items-start justify-between gap-6 flex-wrap">
      <div className="min-w-0 max-w-2xl">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: meta.accent.hex }} />
          NEXUS OS · {meta.eyebrow}
        </div>
        <h2 className="mt-3 text-[1.9rem] sm:text-[2.3rem] leading-[1.12] font-extrabold tracking-[-0.02em] text-slate-900">
          {meta.title}
        </h2>
        <p className="mt-2.5 text-[13.5px] leading-relaxed text-slate-500">{meta.subtitle}</p>
      </div>
      {right && <div className="flex items-center gap-2 flex-wrap">{right}</div>}
    </header>
  );
};

export const LiveChip: React.FC<{ loading?: boolean; offline?: boolean; label?: string }> = ({
  loading,
  offline,
  label,
}) => (
  <span
    className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full border text-[12px] font-semibold ${
      offline
        ? 'bg-amber-50 border-amber-200 text-amber-700'
        : 'bg-emerald-50 border-emerald-200 text-emerald-700'
    }`}
  >
    <span
      className={`w-1.5 h-1.5 rounded-full ${
        loading ? 'bg-slate-400 animate-pulse' : offline ? 'bg-amber-500' : 'bg-emerald-500 animate-pulse'
      }`}
    />
    {label ?? (offline ? 'Backend offline' : 'Live')}
  </span>
);

export const ViewShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="mx-auto w-full max-w-[1180px] px-6 sm:px-10 pt-10 pb-48">{children}</div>
);

export const SkeletonCard: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`rounded-3xl bg-white border border-slate-200/80 p-6 ${className}`}>
    <div className="space-y-3">
      <div className="h-4 w-1/3 rounded-full bg-slate-100 animate-pulse" />
      <div className="h-3 w-2/3 rounded-full bg-slate-100 animate-pulse" />
      <div className="h-3 w-1/2 rounded-full bg-slate-100 animate-pulse" />
    </div>
  </div>
);
