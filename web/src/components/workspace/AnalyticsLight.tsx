import React, { useMemo } from 'react';
import {
  Activity,
  Cpu,
  Database,
  Clock,
  RefreshCw,
  Wrench,
  Share2,
  Zap,
  Gauge,
} from 'lucide-react';
import { PageHeader, ViewShell, LiveChip, useLiveFetch, formatUptime, formatNumber, graphGroupColor } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Analytics Dashboard — KPI telemetry matrix, request distribution,
 * and graph composition, sampled live from the running cortex:
 *   GET /api/system/telemetry · GET /v1/system/health · GET /api/graph
 * ──────────────────────────────────────────────────────────────────────────── */

interface TelemetryPayload {
  status: string;
  uptime_seconds: number;
  backend_mode: string;
  nim: { configured: boolean; has_api_key: boolean; model: string };
  tools_count: number;
  graph_nodes_count: number;
  graph_links_count: number;
  counters: Record<string, number>;
}

interface HealthPayload {
  status: string;
  components: Record<string, string>;
  tools_loaded: number;
}

interface GraphPayload {
  nodes: Array<{ id: string; group?: string }>;
  links: Array<{ source: unknown; target: unknown }>;
}

const COUNTER_LABELS: Record<string, string> = {
  chat: 'Chat / Cortex',
  research: 'Deep research',
  tools: 'Tool calls',
  workflows: 'Workflow runs',
  graph: 'Graph queries',
};

const COUNTER_COLORS: Record<string, string> = {
  chat: '#3B82F6',
  research: '#8B5CF6',
  tools: '#F59E0B',
  workflows: '#10B981',
  graph: '#06B6D4',
};

export const AnalyticsLight: React.FC = () => {
  const telemetry = useLiveFetch<TelemetryPayload>('/api/system/telemetry', 8000);
  const health = useLiveFetch<HealthPayload>('/v1/system/health', 15000);
  const graph = useLiveFetch<GraphPayload>('/api/graph?limit=200');

  const totalRequests = useMemo(
    () =>
      Object.values((telemetry.data?.counters ?? {}) as Record<string, number>).reduce((a, b) => a + b, 0),
    [telemetry.data]
  );

  const composition = useMemo(() => {
    const counts = new Map<string, number>();
    (graph.data?.nodes ?? []).forEach((n) => counts.set(n.group ?? 'Other', (counts.get(n.group ?? 'Other') ?? 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [graph.data]);

  const maxCounter = useMemo(
    () => Math.max(1, ...Object.values((telemetry.data?.counters ?? { a: 1 }) as Record<string, number>)),
    [telemetry.data]
  );

  const t = telemetry.data;
  const offline = !!telemetry.error;

  return (
    <ViewShell>
      <PageHeader
        route="ANALYTICS"
        right={
          <>
            <LiveChip loading={telemetry.loading} offline={offline} label={offline ? 'Telemetry offline' : 'Sampling every 8s'} />
            <button
              onClick={() => {
                telemetry.reload();
                health.reload();
                graph.reload();
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-700 transition-all cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </>
        }
      />

      {/* KPI matrix */}
      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          icon={<Zap className="w-4 h-4 text-blue-500" />}
          label="Total requests"
          value={formatNumber(totalRequests)}
          sub="across all cortex routes"
          loading={telemetry.loading}
        />
        <KpiTile
          icon={<Wrench className="w-4 h-4 text-amber-500" />}
          label="Tools loaded"
          value={String(health.data?.tools_loaded ?? t?.tools_count ?? 0)}
          sub="registered in tool registry"
          loading={telemetry.loading && health.loading}
        />
        <KpiTile
          icon={<Share2 className="w-4 h-4 text-cyan-500" />}
          label="Graph synapses"
          value={formatNumber((t?.graph_nodes_count ?? graph.data?.nodes.length ?? 0) + (t?.graph_links_count ?? graph.data?.links.length ?? 0))}
          sub={`${t?.graph_nodes_count ?? graph.data?.nodes.length ?? 0} nodes · ${t?.graph_links_count ?? graph.data?.links.length ?? 0} links`}
          loading={telemetry.loading && graph.loading}
        />
        <KpiTile
          icon={<Clock className="w-4 h-4 text-emerald-500" />}
          label="Cortex uptime"
          value={formatUptime(t?.uptime_seconds ?? 0)}
          sub={`backend: ${t?.backend_mode ?? '—'}`}
          loading={telemetry.loading}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-4 items-start">
        {/* Request distribution */}
        <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <h3 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-slate-400">
            <Activity className="w-3.5 h-3.5 text-blue-500" /> Request distribution
          </h3>
          <p className="mt-1 text-[11px] nxs-mono text-slate-300">REQUEST_COUNTERS · live</p>
          <div className="mt-5 space-y-4">
            {Object.entries((t?.counters ?? {}) as Record<string, number>).map(([key, value], i) => (
              <div key={key}>
                <div className="flex items-center justify-between text-[12px]">
                  <span className="font-semibold text-slate-600">{COUNTER_LABELS[key] ?? key}</span>
                  <span className="nxs-mono font-bold text-slate-800">{value}</span>
                </div>
                <div className="mt-1.5 h-2.5 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="nxs-bar h-full rounded-full"
                    style={{
                      width: `${Math.max(3, (value / maxCounter) * 100)}%`,
                      backgroundColor: COUNTER_COLORS[key] ?? '#64748B',
                      animationDelay: `${i * 80}ms`,
                    }}
                  />
                </div>
              </div>
            ))}
            {(!t || Object.keys(t.counters ?? {}).length === 0) && (
              <p className="py-6 text-center text-[12.5px] text-slate-400">
                {telemetry.loading ? 'Sampling telemetry…' : 'No requests recorded yet — run the cockpit to fill these gauges.'}
              </p>
            )}
          </div>
        </div>

        {/* Graph composition donut */}
        <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <h3 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-slate-400">
            <Share2 className="w-3.5 h-3.5 text-cyan-500" /> Graph composition
          </h3>
          <p className="mt-1 text-[11px] nxs-mono text-slate-300">nodes by cluster · /api/graph/graph</p>
          <div className="mt-4 flex items-center gap-6 flex-wrap sm:flex-nowrap">
            <DonutChart
              slices={composition.map(([group, count]) => ({ label: group, value: count, color: graphGroupColor(group) }))}
            />
            <div className="flex-1 min-w-[140px] space-y-1.5">
              {composition.slice(0, 8).map(([group, count]) => (
                <div key={group} className="flex items-center gap-2 text-[12px]">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: graphGroupColor(group) }} />
                  <span className="text-slate-600 font-medium">{group}</span>
                  <span className="ml-auto nxs-mono text-slate-800 font-bold">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Component health + NIM */}
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <h3 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-slate-400">
            <Gauge className="w-3.5 h-3.5 text-emerald-500" /> Component health
          </h3>
          <div className="mt-4 grid sm:grid-cols-2 gap-2.5">
            {Object.entries(health.data?.components ?? {}).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between px-3.5 py-2.5 rounded-2xl bg-slate-50 border border-slate-100">
                <span className="text-[12.5px] font-semibold text-slate-600 nxs-mono">{name}</span>
                <span className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  {status}
                </span>
              </div>
            ))}
            {!health.data && (
              <p className="py-4 text-[12.5px] text-slate-400 sm:col-span-2 text-center">
                {health.loading ? 'Probing components…' : 'Health endpoint unreachable.'}
              </p>
            )}
          </div>
        </div>

        <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <h3 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-slate-400">
            <Cpu className="w-3.5 h-3.5 text-amber-500" /> Inference engine
          </h3>
          <div className="mt-4 rounded-2xl bg-gradient-to-br from-[#0B0F19] to-slate-800 p-5 text-white">
            <div className="flex items-center gap-3">
              <span className="w-11 h-11 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-[0_0_24px_rgba(245,158,11,0.4)]">
                <Cpu className="w-5 h-5 text-white" />
              </span>
              <div className="min-w-0">
                <p className="text-[13.5px] font-bold truncate">{t?.nim?.model ?? 'No model bound'}</p>
                <p className="text-[11px] text-slate-400 nxs-mono mt-0.5">NVIDIA NIM · inference provider</p>
              </div>
              <span
                className={`ml-auto px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                  t?.nim?.has_api_key
                    ? 'bg-emerald-500/15 border-emerald-400/40 text-emerald-300'
                    : 'bg-amber-500/15 border-amber-400/40 text-amber-300'
                }`}
              >
                {t?.nim?.has_api_key ? 'Key set' : 'Local mode'}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-white/5 border border-white/10 py-2.5">
                <p className="text-[9.5px] uppercase tracking-wider text-slate-500 font-bold">Configured</p>
                <p className="text-[13px] font-bold nxs-mono mt-0.5">{t?.nim?.configured ? 'Yes' : 'No'}</p>
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 py-2.5">
                <p className="text-[9.5px] uppercase tracking-wider text-slate-500 font-bold">Backend</p>
                <p className="text-[13px] font-bold nxs-mono mt-0.5">{t?.backend_mode ?? '—'}</p>
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 py-2.5">
                <p className="text-[9.5px] uppercase tracking-wider text-slate-500 font-bold">Status</p>
                <p className="text-[13px] font-bold nxs-mono mt-0.5 text-emerald-400">{t?.status ?? '—'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ViewShell>
  );
};

const KpiTile: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  loading?: boolean;
}> = ({ icon, label, value, sub, loading }) => (
  <div className="rounded-3xl bg-white border border-slate-200/80 p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
    <div className="flex items-center justify-between">
      <span className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</span>
      <span className="w-8 h-8 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center">{icon}</span>
    </div>
    {loading ? (
      <div className="mt-2.5 h-8 w-24 rounded-xl bg-slate-100 animate-pulse" />
    ) : (
      <p className="mt-2 text-[26px] leading-none font-extrabold text-slate-900 nxs-mono tracking-tight">{value}</p>
    )}
    <p className="mt-2 text-[11.5px] text-slate-400">{sub}</p>
  </div>
);

const DonutChart: React.FC<{ slices: Array<{ label: string; value: number; color: string }> }> = ({ slices }) => {
  const total = slices.reduce((a, s) => a + s.value, 0) || 1;
  const R = 52;
  const r = 34;
  const cx = 62;
  const cy = 62;
  let angle = -90;

  const arc = (startDeg: number, endDeg: number) => {
    const large = endDeg - startDeg > 180 ? 1 : 0;
    const p1 = polar(cx, cy, R, startDeg);
    const p2 = polar(cx, cy, R, endDeg);
    const p3 = polar(cx, cy, r, endDeg);
    const p4 = polar(cx, cy, r, startDeg);
    return `M ${p1.x} ${p1.y} A ${R} ${R} 0 ${large} 1 ${p2.x} ${p2.y} L ${p3.x} ${p3.y} A ${r} ${r} 0 ${large} 0 ${p4.x} ${p4.y} Z`;
  };

  return (
    <svg viewBox="0 0 124 124" className="w-[124px] h-[124px] shrink-0" role="img" aria-label="Graph composition donut">
      {slices.map((s, i) => {
        const sweep = (s.value / total) * 360;
        const start = angle;
        const end = angle + Math.max(0.5, sweep - 1);
        angle += sweep;
        return <path key={s.label} d={arc(start, end)} fill={s.color} opacity={0.92} style={{ animation: `nxs-rise 0.5s ${i * 60}ms both` }} />;
      })}
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize={17} fontWeight={800} fill="#0F172A">
        {total}
      </text>
      <text x={cx} y={cy + 13} textAnchor="middle" fontSize={8} fill="#94A3B8" letterSpacing={1}>
        NODES
      </text>
    </svg>
  );
};

function polar(cx: number, cy: number, r: number, deg: number): { x: number; y: number } {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}
