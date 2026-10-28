import React from 'react';
import {
  ArrowUpRight,
  Activity,
  Cpu,
  Database,
  Clock,
  Sparkles,
  Zap,
  Users,
  CalendarRange,
  Bot,
  Layers3,
  Search,
} from 'lucide-react';
import { WorkspaceRoute } from './shared';
import { RobotCompanion } from './RobotCompanion';

/* ────────────────────────────────────────────────────────────────────────────
 * The Primary Workspace Dashboard home surface — greeting header, feature
 * matrix, system pulse, and the animated robot onboarding hero.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface BootstrapData {
  greeting: { user: string; headline: string; subline: string };
  hero: { companion: string; message: string; suggestions: string[] };
  cards: Array<{ id: string; title: string; description: string; accent: string; action: string; stat: string }>;
  telemetry: {
    uptime_seconds: number;
    agents_online: number;
    agents: Array<{ name: string; role: string; status: string }>;
    recent_memories: Array<{ content: string; memory_type: string; access_count: number }>;
    nim_online: boolean;
    nim_model: string | null;
  };
}

function formatUptimeLocal(seconds: number): string {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

interface WorkspaceHomeProps {
  bootstrap: BootstrapData;
  backendOnline: boolean | null;
  isBusy: boolean;
  heroDismissed: boolean;
  onDismissHero: () => void;
  onRouteChange: (route: WorkspaceRoute) => void;
  onOpenSpaces?: () => void;
  onFastStart: (query: string) => void;
  onSuggestion: (s: string) => void;
  onBoost: () => void;
}

export const WorkspaceHome: React.FC<WorkspaceHomeProps> = ({
  bootstrap,
  backendOnline,
  isBusy,
  heroDismissed,
  onDismissHero,
  onRouteChange,
  onOpenSpaces,
  onFastStart,
  onSuggestion,
  onBoost,
}) => {
  const cards = bootstrap.cards;
  const telemetry = bootstrap.telemetry;

  const handleCardAction = (action: string) => {
    if (action === 'OPEN_AGENTS') onRouteChange('AGENTS');
    else if (action === 'OPEN_WORKFLOWS') onRouteChange('WORKFLOW');
    else if (action === 'FAST_START')
      onFastStart('Break down my next contribution into three quick wins I can ship today.');
  };

  return (
    <div className="mx-auto w-full max-w-[1180px] px-6 sm:px-10 pt-12 pb-48">
      {/* ── Top Header ─────────────────────────────────────────────────── */}
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                backendOnline === null
                  ? 'bg-slate-300 animate-pulse'
                  : backendOnline
                    ? 'bg-emerald-500 animate-pulse'
                    : 'bg-amber-500'
              }`}
            />
            NEXUS OS · Workspace
            <span className="text-slate-300">/</span>
            <span className="text-slate-500 normal-case tracking-normal font-medium">
              {backendOnline === false ? 'Backend offline — showing local fallback' : 'Light Canvas Interface'}
            </span>
          </div>

          <h1 className="mt-4 text-[2.1rem] sm:text-[2.9rem] leading-[1.08] font-extrabold tracking-[-0.02em] text-slate-900">
            {bootstrap.greeting.headline.split(',').map((part, i) =>
              i === 0 ? (
                <span key={i} className="text-slate-400">
                  {part},
                </span>
              ) : (
                <span key={i}>{part}</span>
              )
            )}
          </h1>

          <p className="mt-4 text-[15px] leading-relaxed text-slate-500 max-w-[560px]">{bootstrap.greeting.subline}</p>
        </div>

        {/* Top-right cluster — live status (the brief's Upgrade pill was
            intentionally removed per instruction). */}
        <div className="hidden lg:flex items-center gap-2.5 pt-1">
          <span
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full border text-[12px] font-semibold ${
              backendOnline ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-slate-200 text-slate-500'
            }`}
            title={telemetry.nim_model ? `NVIDIA NIM · ${telemetry.nim_model}` : 'NIM provider status'}
          >
            <Cpu className="w-3.5 h-3.5" strokeWidth={2} />
            {backendOnline ? 'Cortex Online' : 'Cortex Offline'}
          </span>
          <span
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600"
            title="Autonomous agents reporting to the swarm"
          >
            <Users className="w-3.5 h-3.5 text-violet-500" strokeWidth={2} />
            {telemetry.agents_online} agents
          </span>
          <span
            className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-400 via-slate-700 to-violet-500 border-2 border-white shadow-md flex items-center justify-center text-white text-[13px] font-bold"
            title={`Signed in as ${bootstrap.greeting.user}`}
          >
            {bootstrap.greeting.user.slice(0, 1).toUpperCase()}
          </span>
        </div>
      </header>

      {/* ── Feature Matrix Grid ────────────────────────────────────────── */}
      <section aria-label="Feature matrix" className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Card 1 — Fast Start (orange geometric icon) */}
        <button
          onClick={() => handleCardAction(cards[0]?.action ?? 'FAST_START')}
          className="nxs-card group text-left bg-white rounded-3xl border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] hover:border-orange-200 hover:shadow-[0_24px_50px_-24px_rgba(249,115,22,0.35)] cursor-pointer"
        >
          <div className="flex items-start justify-between">
            <span className="w-14 h-14 rounded-2xl bg-gradient-to-br from-orange-50 to-amber-100 border border-orange-100 flex items-center justify-center">
              <svg viewBox="0 0 48 48" className="w-9 h-9" aria-hidden>
                <path d="M9 8 L23 8 L9 22 Z" fill="#FDBA74" />
                <circle cx="33" cy="15" r="8.5" fill="#F97316" />
                <rect x="10" y="27" width="15" height="15" rx="3.5" fill="#FB923C" />
                <rect x="29" y="27" width="10" height="10" rx="2.5" fill="#FFEDD5" stroke="#FDBA74" strokeWidth="2" />
              </svg>
            </span>
            <ArrowUpRight className="w-4 h-4 text-slate-300 group-hover:text-orange-500 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
          </div>
          <h3 className="mt-5 text-[17px] font-bold text-slate-900">{cards[0]?.title ?? 'Fast Start'}</h3>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
            {cards[0]?.description ?? 'Spin up quick tasks and contribution loops. Zero-friction execution, instant feedback.'}
          </p>
          <div className="mt-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-orange-600">
            <Zap className="w-3.5 h-3.5" strokeWidth={2.2} />
            {cards[0]?.stat ?? 'Quick task execution'}
          </div>
        </button>

        {/* Card 2 — Collaborate with Team (multi-colored collaborative grid) */}
        <button
          onClick={() => handleCardAction(cards[1]?.action ?? 'OPEN_AGENTS')}
          className="nxs-card group text-left bg-white rounded-3xl border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] hover:border-violet-200 hover:shadow-[0_24px_50px_-24px_rgba(139,92,246,0.35)] cursor-pointer"
        >
          <div className="flex items-start justify-between">
            <span className="w-14 h-14 rounded-2xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200/80 flex items-center justify-center">
              <svg viewBox="0 0 48 48" className="w-9 h-9" aria-hidden>
                <rect x="7" y="7" width="15.5" height="15.5" rx="4" fill="#22D3EE" />
                <rect x="25.5" y="7" width="15.5" height="15.5" rx="4" fill="#A78BFA" />
                <rect x="7" y="25.5" width="15.5" height="15.5" rx="4" fill="#FBBF24" />
                <rect x="25.5" y="25.5" width="15.5" height="15.5" rx="4" fill="#34D399" />
                <circle cx="33.2" cy="33.2" r="4.2" fill="#FFFFFF" opacity="0.9" />
              </svg>
            </span>
            <ArrowUpRight className="w-4 h-4 text-slate-300 group-hover:text-violet-500 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
          </div>
          <h3 className="mt-5 text-[17px] font-bold text-slate-900">{cards[1]?.title ?? 'Collaborate with Team'}</h3>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
            {cards[1]?.description ?? 'Background multi-agent orchestrations — researcher, coder, planner and swarm run in parallel.'}
          </p>
          <div className="mt-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-violet-600">
            <Bot className="w-3.5 h-3.5" strokeWidth={2.2} />
            {cards[1]?.stat ?? 'Multi-agent orchestration'}
          </div>
        </button>

        {/* Card 3 — Planning (blue application calendar) */}
        <button
          onClick={() => handleCardAction(cards[2]?.action ?? 'OPEN_WORKFLOWS')}
          className="nxs-card group text-left bg-white rounded-3xl border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] hover:border-blue-200 hover:shadow-[0_24px_50px_-24px_rgba(59,130,246,0.35)] cursor-pointer"
        >
          <div className="flex items-start justify-between">
            <span className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-50 to-sky-100 border border-blue-100 flex items-center justify-center">
              <svg viewBox="0 0 48 48" className="w-9 h-9" aria-hidden>
                <rect x="6" y="10" width="36" height="32" rx="6" fill="#EFF6FF" stroke="#2563EB" strokeWidth="2.6" />
                <rect x="6" y="10" width="36" height="10" rx="6" fill="#2563EB" />
                <rect x="6" y="16" width="36" height="4" fill="#2563EB" />
                <rect x="14" y="5" width="4" height="8" rx="2" fill="#1D4ED8" />
                <rect x="30" y="5" width="4" height="8" rx="2" fill="#1D4ED8" />
                <circle cx="17" cy="31" r="2.6" fill="#2563EB" />
                <circle cx="24" cy="31" r="2.6" fill="#93C5FD" />
                <circle cx="31" cy="31" r="2.6" fill="#93C5FD" />
              </svg>
            </span>
            <ArrowUpRight className="w-4 h-4 text-slate-300 group-hover:text-blue-500 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
          </div>
          <h3 className="mt-5 text-[17px] font-bold text-slate-900">{cards[2]?.title ?? 'Planning'}</h3>
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
            {cards[2]?.description ?? 'Track priorities and workflows on a living calendar. Deadlines become DAG steps.'}
          </p>
          <div className="mt-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-600">
            <CalendarRange className="w-3.5 h-3.5" strokeWidth={2.2} />
            {cards[2]?.stat ?? 'Priorities & workflows'}
          </div>
        </button>
      </section>

      {/* ── Upgrade Spaces — searchable platform capability catalog ─────── */}
      {onOpenSpaces && (
        <section className="relative mt-6 overflow-hidden rounded-[2rem] bg-slate-950 px-6 py-6 text-white shadow-[0_28px_60px_-30px_rgba(15,23,42,0.7)] sm:px-8">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-28 h-64 w-64 rounded-full bg-cyan-400/20 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -bottom-32 left-1/3 h-64 w-64 rounded-full bg-violet-500/20 blur-3xl" />
          <div className="relative flex flex-wrap items-center gap-5">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl border border-white/15 bg-white/10">
              <Layers3 className="h-7 w-7 text-cyan-300" strokeWidth={1.7} />
            </span>
            <div className="min-w-[240px] flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-extrabold tracking-tight">Upgrade Spaces</h2>
                <span className="rounded-full border border-emerald-300/30 bg-emerald-400/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-200">
                  10 landed
                </span>
              </div>
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-300">
                Search semantic memory, swarm state, routing, consensus, bridge security, telemetry and more — with
                evidence paths and honest runtime activation notes.
              </p>
            </div>
            <button
              type="button"
              onClick={onOpenSpaces}
              className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-bold text-slate-950 shadow-lg transition-all hover:-translate-y-0.5 hover:bg-cyan-100"
            >
              <Search className="h-4 w-4" />
              Explore spaces
              <ArrowUpRight className="h-4 w-4" />
            </button>
          </div>
        </section>
      )}

      {/* ── Onboarding Hero (center-right) + System Pulse ──────────────── */}
      <section className="mt-8 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* System pulse — live telemetry from the bootstrap route */}
        <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.16em] text-slate-400">
              <Activity className="w-4 h-4 text-cyan-600" strokeWidth={2.2} />
              System Pulse
            </h3>
            <span className="text-[10px] nxs-mono text-slate-400">GET /api/workspace/bootstrap</span>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-2xl bg-slate-50 border border-slate-100 p-3.5">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                <Clock className="w-3 h-3" /> Uptime
              </div>
              <div className="mt-1.5 text-[18px] font-extrabold text-slate-900 nxs-mono">
                {formatUptimeLocal(telemetry.uptime_seconds)}
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50 border border-slate-100 p-3.5">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                <Users className="w-3 h-3" /> Agents
              </div>
              <div className="mt-1.5 text-[18px] font-extrabold text-slate-900 nxs-mono">
                {telemetry.agents_online}
                <span className="text-[12px] text-slate-400 font-semibold"> online</span>
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50 border border-slate-100 p-3.5">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                <Database className="w-3 h-3" /> NIM
              </div>
              <div className="mt-1.5 text-[18px] font-extrabold text-slate-900 nxs-mono">
                {telemetry.nim_online ? <span className="text-emerald-600">Ready</span> : <span className="text-amber-600">Local</span>}
              </div>
            </div>
          </div>

          {/* Agent roster */}
          {telemetry.agents.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {telemetry.agents.slice(0, 8).map((a, i) => (
                <span
                  key={`${a.name}-${i}`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-50 border border-violet-100 text-[11px] font-semibold text-violet-700"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                  {a.name}
                </span>
              ))}
            </div>
          )}

          {/* Recent memories */}
          {telemetry.recent_memories.length > 0 ? (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <h4 className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400 mb-2.5">Recent Memory Synapses</h4>
              <ul className="space-y-2">
                {telemetry.recent_memories.slice(0, 3).map((m, i) => (
                  <li key={i} className="flex gap-2.5 items-start">
                    <span className="shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <div className="min-w-0">
                      <p className="text-[12.5px] text-slate-600 leading-snug line-clamp-2">{m.content}</p>
                      <span className="text-[10px] nxs-mono text-slate-400">
                        {m.memory_type} · {m.access_count} recalls
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-4 pt-4 border-t border-slate-100 text-[12.5px] text-slate-400 leading-relaxed">
              No episodic memories yet — every cockpit action you run writes new synapses into the second brain.
            </p>
          )}
        </div>

        {/* Animated onboarding hero — floating robot companion */}
        <div className="lg:col-span-5 flex items-center justify-center py-2">
          {!heroDismissed ? (
            <RobotCompanion
              companion={bootstrap.hero.companion}
              message={bootstrap.hero.message}
              suggestions={bootstrap.hero.suggestions}
              onSuggestion={onSuggestion}
              onBoost={onBoost}
              onDismiss={onDismissHero}
              isBusy={isBusy}
            />
          ) : (
            <button
              onClick={onDismissHero}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-white border border-slate-200 text-[13px] font-semibold text-slate-600 hover:border-cyan-300 hover:text-cyan-700 transition-all shadow-sm cursor-pointer"
            >
              <Sparkles className="w-4 h-4 text-cyan-500" />
              Summon {bootstrap.hero.companion}
            </button>
          )}
        </div>
      </section>
    </div>
  );
};
