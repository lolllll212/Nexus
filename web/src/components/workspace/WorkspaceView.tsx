import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
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
} from 'lucide-react';
import { OperatingMode } from '../../types';
import { nexusJson, nexusChatStream } from '../../api';
import { WorkspaceNavRail } from './WorkspaceNavRail';
import { RobotCompanion } from './RobotCompanion';
import { QueryConsole, ConsoleMode, ConsoleStatus } from './QueryConsole';
import { WorkspaceResults, WorkspaceResult } from './WorkspaceResults';

/* ────────────────────────────────────────────────────────────────────────────
 * NEXUS OS — Primary Workspace Dashboard (light canvas) + Advanced System
 * Cockpit (floating query console).
 *
 * Everything on this screen is wired to the live backend:
 *   • Header greeting, hero copy, card stats  ← GET  /api/workspace/bootstrap
 *   • Fast Start card                        → focuses the cockpit
 *   • Collaborate card                       → Agent Orchestration modal
 *   • Planning card                          → Workflow Canvas mode
 *   • Deep Research chip                     → POST /api/research/execute
 *   • Make an Image chip                     → POST /api/workspace/image
 *   • Search chip                            → POST /api/workspace/search
 *   • Create music chip                      → POST /api/workspace/music
 *   • Plain Enter                            → POST /v1/chat/stream (SSE)
 *
 * NOTE: the original brief placed a dark "Upgrade" pill in the top-right
 * corner. Per the follow-up instruction ("remove the upgrade sign") it was
 * intentionally removed — the top-right cluster now shows live system status.
 * ──────────────────────────────────────────────────────────────────────────── */

interface BootstrapData {
  greeting: { user: string; headline: string; subline: string };
  hero: { companion: string; message: string; suggestions: string[] };
  cards: Array<{
    id: string;
    title: string;
    description: string;
    accent: string;
    action: string;
    stat: string;
  }>;
  telemetry: {
    uptime_seconds: number;
    agents_online: number;
    agents: Array<{ name: string; role: string; status: string }>;
    recent_memories: Array<{ content: string; memory_type: string; access_count: number }>;
    nim_online: boolean;
    nim_model: string | null;
  };
}

const FALLBACK_BOOTSTRAP: BootstrapData = {
  greeting: {
    user: 'Nixtio',
    headline: 'Hi Nixtio, Ready to Achieve Great Things?',
    subline: 'Your cognitive copilot is online. Search, research, create, and ship — all from one canvas.',
  },
  hero: {
    companion: 'NIX-7',
    message: 'Hey there! Need a boost?',
    suggestions: [
      'Explain quantum computing in simple terms',
      'Research the state of autonomous agents',
      'Generate an aurora over a neural skyline',
      'Compose a focus track for deep work',
    ],
  },
  cards: [
    {
      id: 'fast-start',
      title: 'Fast Start',
      description: 'Spin up quick tasks and contribution loops. Zero-friction execution, instant feedback.',
      accent: 'orange',
      action: 'FAST_START',
      stat: 'Ready when you are',
    },
    {
      id: 'collaborate',
      title: 'Collaborate with Team',
      description: 'Background multi-agent orchestrations — researcher, coder, planner and swarm run in parallel.',
      accent: 'multicolor',
      action: 'OPEN_AGENTS',
      stat: 'Swarm standing by',
    },
    {
      id: 'planning',
      title: 'Planning',
      description: 'Track priorities and workflows on a living calendar. Deadlines become DAG steps.',
      accent: 'blue',
      action: 'OPEN_WORKFLOWS',
      stat: 'Roadmap synced',
    },
  ],
  telemetry: {
    uptime_seconds: 0,
    agents_online: 0,
    agents: [],
    recent_memories: [],
    nim_online: false,
    nim_model: null,
  },
};

const RESEARCH_STAGES = [
  'Decomposing query',
  'Searching the web',
  'Browsing sources',
  'Corroborating claims',
  'Synthesising findings',
  'Ingesting into graph',
];

const IMAGE_STAGES = ['Seeding palette', 'Composing geometry', 'Rendering vectors'];
const MUSIC_STAGES = ['Choosing key & scale', 'Arranging progression', 'Rendering waveform'];

function formatUptime(seconds: number): string {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

interface WorkspaceViewProps {
  onNavigate: (mode: OperatingMode) => void;
  onOpenAgents: () => void;
  onOpenIntegrations: () => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ onNavigate, onOpenAgents, onOpenIntegrations }) => {
  const [bootstrap, setBootstrap] = useState<BootstrapData>(FALLBACK_BOOTSTRAP);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const [consoleValue, setConsoleValue] = useState('');
  const [consoleMode, setConsoleMode] = useState<ConsoleMode>('chat');
  const [consoleStatus, setConsoleStatus] = useState<ConsoleStatus>('idle');
  const [statusDetail, setStatusDetail] = useState('');
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [heroDismissed, setHeroDismissed] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const stageTimerRef = useRef<number | null>(null);
  const resultAnchorRef = useRef<HTMLDivElement | null>(null);

  const isBusy = consoleStatus !== 'idle';

  /* ── Live bootstrap pull ──────────────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await nexusJson<BootstrapData>('/api/workspace/bootstrap');
        if (!cancelled) {
          setBootstrap(data);
          setBackendOnline(true);
        }
      } catch {
        if (!cancelled) setBackendOnline(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ── Stage ticker: visualises the background execution stream ─────────── */
  const startStages = useCallback((stages: string[]) => {
    let i = 0;
    if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
    setStatusDetail(stages[0]);
    stageTimerRef.current = window.setInterval(() => {
      i = Math.min(i + 1, stages.length - 1);
      setStatusDetail(stages[i]);
    }, 2100);
  }, []);

  const stopStages = useCallback(() => {
    if (stageTimerRef.current) {
      window.clearInterval(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopStages(), [stopStages]);

  /* ── Bring fresh results into view above the floating cockpit ─────────── */
  useEffect(() => {
    if (result) {
      resultAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [result?.id]);

  /* ── The cockpit executor — every mode maps to a real backend route ───── */
  const runQuery = useCallback(
    async (rawQuery: string, mode: ConsoleMode) => {
      const query = rawQuery.trim();
      if (!query || consoleStatus !== 'idle') return;

      setConsoleValue('');
      setResult(null);
      setConsoleStatus('thinking');
      setStatusDetail(
        mode === 'research' ? 'Background research stream' : mode === 'chat' ? 'Cortex ReAct loop' : 'Dispatching'
      );

      const id = `res-${Date.now()}`;
      let stagesStarted = false;

      try {
        /* ── Plain ask: true SSE stream through the cognitive loop ──────── */
        if (mode === 'chat') {
          const steps: string[] = [];
          let answer = '';
          let sawAnswer = false;

          await nexusChatStream(query, 'general', (ev) => {
            if (ev.type === 'thought' && ev.content) {
              steps.push(ev.content.slice(0, 180));
            } else if (ev.type === 'tool_call') {
              steps.push(`→ tool call: ${ev.tool_id ?? 'tool'}`);
            } else if (ev.type === 'observation' && ev.content) {
              steps.push(`← ${ev.content.slice(0, 140)}`);
            } else if ((ev.type === 'answer' || ev.type === 'content') && ev.content) {
              if (!sawAnswer) {
                sawAnswer = true;
                setConsoleStatus('streaming');
                setStatusDetail('Answer streaming');
              }
              answer += ev.content;
              setResult({ kind: 'chat', id, query, answer, steps, streaming: true });
            }
          });

          setResult((prev) =>
            prev && prev.kind === 'chat' && prev.id === id
              ? { ...prev, streaming: false }
              : {
                  kind: 'chat',
                  id,
                  query,
                  answer:
                    answer ||
                    'The cortex completed the loop without returning an answer. The configured LLM endpoint may be unreachable — check /api/nim/status and resend.',
                  steps,
                  streaming: false,
                }
          );
        }

        /* ── Deep Research: background multi-hop execution stream ───────── */
        else if (mode === 'research') {
          stagesStarted = true;
          startStages(RESEARCH_STAGES);
          const data = await nexusJson<any>('/api/research/execute', {
            method: 'POST',
            body: JSON.stringify({ query, max_sources: 3 }),
          });
          setResult({
            kind: 'research',
            id,
            query,
            summary: data.summary ?? 'Research complete.',
            keyFindings: data.key_findings ?? [],
            concepts: data.extracted_concepts ?? [],
            sources: (data.sources ?? []).map((s: any) => ({ title: s.title, url: s.url, snippet: s.snippet })),
            nodesAdded: data.nodes_added_to_graph ?? 0,
            durationSeconds: data.duration_seconds ?? 0,
          });
        }

        /* ── Make an Image: procedural art engine ───────────────────────── */
        else if (mode === 'image') {
          stagesStarted = true;
          startStages(IMAGE_STAGES);
          const data = await nexusJson<any>('/api/workspace/image', {
            method: 'POST',
            body: JSON.stringify({ prompt: query }),
          });
          setResult({
            kind: 'image',
            id,
            query,
            svgDataUri: data.svg_data_uri,
            palette: data.palette ?? [],
            seed: data.seed,
            style: data.style,
            renderMs: data.render_ms ?? 0,
          });
        }

        /* ── Search: unified multi-modal retrieval ──────────────────────── */
        else if (mode === 'search') {
          startStages(['Scanning memory', 'Walking graph', 'Merging corpora']);
          const data = await nexusJson<any>('/api/workspace/search', {
            method: 'POST',
            body: JSON.stringify({ query, limit: 8 }),
          });
          setResult({
            kind: 'search',
            id,
            query,
            results: data.results ?? [],
            scannedSources: data.scanned_sources ?? 0,
            durationMs: data.duration_ms ?? 0,
          });
        }

        /* ── Create music: generative audio cortex ──────────────────────── */
        else if (mode === 'music') {
          stagesStarted = true;
          startStages(MUSIC_STAGES);
          const data = await nexusJson<any>('/api/workspace/music', {
            method: 'POST',
            body: JSON.stringify({ prompt: query }),
          });
          setResult({
            kind: 'music',
            id,
            query,
            audioDataUri: data.audio_data_uri,
            keyName: data.key,
            scale: data.scale,
            tempo: data.tempo,
            durationSeconds: data.duration_seconds,
            notesRendered: data.notes_rendered,
            renderMs: data.render_ms ?? 0,
          });
        }
      } catch (err: any) {
        setResult({
          kind: 'error',
          id,
          query,
          message: err?.message ?? 'The backend route failed to respond.',
        });
      } finally {
        if (stagesStarted) stopStages();
        setConsoleStatus('idle');
        setStatusDetail('');
      }
    },
    [consoleStatus, startStages, stopStages]
  );

  /* ── Card + hero wiring ────────────────────────────────────────────────── */
  const handleCardAction = useCallback(
    (action: string) => {
      if (action === 'OPEN_AGENTS') onOpenAgents();
      else if (action === 'OPEN_WORKFLOWS') onNavigate('WORKFLOW');
      else if (action === 'FAST_START') {
        setConsoleValue('Break down my next contribution into three quick wins I can ship today.');
        textareaRef.current?.focus();
      }
    },
    [onNavigate, onOpenAgents]
  );

  const handleSuggestion = useCallback((s: string) => {
    setConsoleValue(s);
    textareaRef.current?.focus();
  }, []);

  const handleBoost = useCallback(() => {
    runQuery(
      'Give me a boost: suggest one high-impact task I can complete in the next hour, and why it matters.',
      'chat'
    );
  }, [runQuery]);

  const cards = bootstrap.cards;
  const telemetry = bootstrap.telemetry;

  return (
    <div className="nxs-workspace fixed inset-0 z-40 bg-[#F9FAFB] overflow-y-auto antialiased text-slate-900">
      <WorkspaceNavRail
        currentMode="WORKSPACE"
        onNavigate={onNavigate}
        onOpenAgents={onOpenAgents}
        onOpenIntegrations={onOpenIntegrations}
      />

      <div className="pl-[72px] min-h-full flex flex-col">
        <div className="w-full max-w-[1180px] mx-auto px-6 sm:px-10 pt-12 pb-56 flex-1">
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
                {bootstrap.greeting.headline.split(',').map((part, i, arr) =>
                  i === 0 ? (
                    <span key={i} className="text-slate-400">
                      {part},
                    </span>
                  ) : (
                    <span key={i}>{part}</span>
                  )
                )}
              </h1>

              <p className="mt-4 text-[15px] leading-relaxed text-slate-500 max-w-[560px]">
                {bootstrap.greeting.subline}
              </p>
            </div>

            {/* Top-right cluster. The brief's "Upgrade" pill was intentionally
                removed per follow-up instruction — replaced by live status. */}
            <div className="hidden lg:flex items-center gap-2.5 pt-1">
              <span
                className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full border text-[12px] font-semibold ${
                  backendOnline
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                    : 'bg-white border-slate-200 text-slate-500'
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
                {/* Orange geometric mark: triangle · circle · square */}
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
                {cards[0]?.description ??
                  'Spin up quick tasks and contribution loops. Zero-friction execution, instant feedback.'}
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
                  {/* Multi-colored collaborative grid */}
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
                {cards[1]?.description ??
                  'Background multi-agent orchestrations — researcher, coder, planner and swarm run in parallel.'}
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
                  {/* Blue application calendar */}
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
                {cards[2]?.description ??
                  'Track priorities and workflows on a living calendar. Deadlines become DAG steps.'}
              </p>
              <div className="mt-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-600">
                <CalendarRange className="w-3.5 h-3.5" strokeWidth={2.2} />
                {cards[2]?.stat ?? 'Priorities & workflows'}
              </div>
            </button>
          </section>

          {/* ── Onboarding Hero (center-right) + System Pulse ──────────────── */}
          <section className="mt-8 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
            {/* System pulse — live telemetry from the bootstrap route */}
            <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.16em] text-slate-400">
                  <Activity className="w-4 h-4 text-cyan-600" strokeWidth={2.2} />
                  System Pulse
                </h3>
                <span className="text-[10px] nxs-mono text-slate-400">
                  GET /api/workspace/bootstrap
                </span>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-2xl bg-slate-50 border border-slate-100 p-3.5">
                  <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                    <Clock className="w-3 h-3" /> Uptime
                  </div>
                  <div className="mt-1.5 text-[18px] font-extrabold text-slate-900 nxs-mono">
                    {formatUptime(telemetry.uptime_seconds)}
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
                    {telemetry.nim_online ? (
                      <span className="text-emerald-600">Ready</span>
                    ) : (
                      <span className="text-amber-600">Local</span>
                    )}
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
                  <h4 className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400 mb-2.5">
                    Recent Memory Synapses
                  </h4>
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
                  onSuggestion={handleSuggestion}
                  onBoost={handleBoost}
                  onDismiss={() => setHeroDismissed(true)}
                  isBusy={isBusy}
                />
              ) : (
                <button
                  onClick={() => setHeroDismissed(false)}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-white border border-slate-200 text-[13px] font-semibold text-slate-600 hover:border-cyan-300 hover:text-cyan-700 transition-all shadow-sm cursor-pointer"
                >
                  <Sparkles className="w-4 h-4 text-cyan-500" />
                  Summon {bootstrap.hero.companion}
                </button>
              )}
            </div>
          </section>

          {/* ── Results anchor + live results ─────────────────────────────── */}
          <div ref={resultAnchorRef} />
          {result && (
            <WorkspaceResults
              key={result.id}
              result={result}
              onClose={() => setResult(null)}
            />
          )}
        </div>
      </div>

      {/* ── SCREEN 2: Floating Query Console (dark graphite cockpit) ──────── */}
      <div className="fixed inset-x-0 bottom-6 z-40 pl-[72px] pointer-events-none">
        <div className="max-w-[880px] mx-auto px-6 pointer-events-auto">
          <QueryConsole
            value={consoleValue}
            onChange={setConsoleValue}
            onSubmit={runQuery}
            status={consoleStatus}
            statusDetail={statusDetail}
            activeMode={consoleMode}
            onModeChange={setConsoleMode}
            textareaRef={textareaRef}
          />
        </div>
      </div>
    </div>
  );
};
