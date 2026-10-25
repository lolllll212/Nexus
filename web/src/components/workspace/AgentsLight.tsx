import React, { useEffect, useMemo, useState } from 'react';
import { Bot, Plus, Radio, RefreshCw, Wrench, ChevronRight, Sparkles, ArrowRight } from 'lucide-react';
import { nexusJson } from '../../api';
import { PageHeader, ViewShell, LiveChip, useLiveFetch } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Agent Orchestration — the swarm roster.
 * Live registrations from GET /v1/agents, the built-in standby
 * roster as fallback, real commissioning via POST /v1/agents, and a
 * simulated inter-agent message bus for mesh telemetry ambience.
 * ──────────────────────────────────────────────────────────────────────────── */

interface LiveAgent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  tools: string[];
  status: string;
}

const BUILTIN_ROSTER: Array<{ name: string; role: string; specialty: string }> = [
  { name: 'Researcher', role: 'research', specialty: 'Multi-hop web research & claim corroboration' },
  { name: 'Coder', role: 'code', specialty: 'Sandboxed Python execution & test harnesses' },
  { name: 'Planner', role: 'planning', specialty: 'Task decomposition & DAG construction' },
  { name: 'Browser', role: 'web', specialty: 'Autonomous navigation & page extraction' },
  { name: 'Vision', role: 'perception', specialty: 'Image/video understanding via multimodal bridge' },
  { name: 'Data Analyst', role: 'analysis', specialty: 'Statistics, trends & anomaly detection' },
  { name: 'Writer', role: 'writing', specialty: 'Briefings, docs & voice synthesis scripts' },
  { name: 'Executor', role: 'execution', specialty: 'Workflow step dispatch & retries' },
  { name: 'Memory', role: 'memory', specialty: 'Episodic recall & synaptic consolidation' },
  { name: 'Fact Checker', role: 'verification', specialty: 'Citation audits & contradiction sweeps' },
];

const ROLE_COLORS: Record<string, string> = {
  research: '#8B5CF6',
  code: '#F59E0B',
  planning: '#3B82F6',
  web: '#06B6D4',
  perception: '#F43F5E',
  analysis: '#10B981',
  writing: '#EC4899',
  execution: '#6366F1',
  memory: '#14B8A6',
  verification: '#84CC16',
};

const BUS_TEMPLATES = [
  '{a} → {b}: claim tree expanded, 3 branches pending corroboration',
  '{a} → {b}: handoff accepted, sandbox warmed in 212ms',
  '{b} → {a}: citation audit passed (confidence 0.94)',
  '{a} → Memory: episodic trace stored for session consolidation',
  '{b} → {a}: DAG step 2/5 completed, telemetry attached',
  '{a} → {b}: requesting retrieval pass on concept cluster',
  '{b} → Planner: proposing schedule rebalance for 2 tasks',
  '{a} → {b}: contradiction detected — spawning verification branch',
];

function roleColor(role: string): string {
  return ROLE_COLORS[role?.toLowerCase()] ?? '#64748B';
}

export const AgentsLight: React.FC = () => {
  const live = useLiveFetch<LiveAgent[]>('/v1/agents', 12000);
  const [commissioning, setCommissioning] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', role: 'research', prompt: '' });
  const [formError, setFormError] = useState<string | null>(null);
  const [busMessages, setBusMessages] = useState<Array<{ id: number; text: string }>>([]);

  const roster = useMemo(() => {
    const liveAgents = live.data ?? [];
    if (liveAgents.length > 0) {
      return liveAgents.map((a) => ({
        name: a.name,
        role: a.role,
        specialty: a.system_prompt ? a.system_prompt.slice(0, 90) : 'Live commissioned agent',
        tools: a.tools ?? [],
        status: a.status,
        live: true,
      }));
    }
    return BUILTIN_ROSTER.map((a) => ({ ...a, tools: [] as string[], status: 'standby', live: false }));
  }, [live.data]);

  const liveCount = roster.filter((r) => r.live).length;

  // Simulated inter-agent bus (clearly labelled)
  useEffect(() => {
    const names = roster.slice(0, 8).map((r) => r.name);
    if (names.length < 2) return;
    let id = 0;
    const push = () => {
      const a = names[Math.floor(Math.random() * names.length)];
      let b = names[Math.floor(Math.random() * names.length)];
      while (b === a) b = names[Math.floor(Math.random() * names.length)];
      const template = BUS_TEMPLATES[Math.floor(Math.random() * BUS_TEMPLATES.length)];
      setBusMessages((prev) => [...prev.slice(-4), { id: id++, text: template.replace('{a}', a).replace('{b}', b) }]);
    };
    push();
    push();
    const timer = window.setInterval(push, 2600);
    return () => window.clearInterval(timer);
  }, [roster]);

  const commissionAgent = async () => {
    if (!form.name.trim() || commissioning) return;
    setCommissioning(true);
    setFormError(null);
    try {
      await nexusJson('/v1/agents', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name.trim(),
          role: form.role,
          system_prompt: form.prompt.trim() || `You are ${form.name.trim()}, a specialized ${form.role} agent in the NEXUS swarm.`,
        }),
      });
      setForm({ name: '', role: 'research', prompt: '' });
      setShowForm(false);
      live.reload();
    } catch (err: any) {
      setFormError(err?.message ?? 'Commissioning failed.');
    } finally {
      setCommissioning(false);
    }
  };

  return (
    <ViewShell>
      <PageHeader
        route="AGENTS"
        right={
          <>
            <LiveChip loading={live.loading} offline={!!live.error} label={live.error ? 'Swarm registry offline' : `${liveCount} live · ${roster.length - liveCount} standby`} />
            <button
              onClick={live.reload}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600 hover:border-indigo-300 hover:text-indigo-700 transition-all cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </>
        }
      />

      {/* Commission bar */}
      <div className="mt-6 rounded-3xl bg-white border border-slate-200/80 p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white flex items-center justify-center">
              <Bot className="w-5 h-5" />
            </span>
            <div>
              <p className="text-[14px] font-bold text-slate-900">Commission a new agent</p>
              <p className="text-[12px] text-slate-400 mt-0.5">
                Registers a live agent in the swarm registry — POST /v1/agents
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowForm((s) => !s)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 transition-all cursor-pointer"
          >
            <Plus className={`w-4 h-4 transition-transform ${showForm ? 'rotate-45' : ''}`} />
            {showForm ? 'Cancel' : 'New agent'}
          </button>
        </div>

        {showForm && (
          <div className="mt-4 pt-4 border-t border-slate-100 grid sm:grid-cols-[1fr_180px_auto] gap-2.5 animate-[nxs-rise_0.3s_ease-out]">
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Agent name — e.g. Cartographer"
              className="px-4 py-2.5 rounded-2xl bg-slate-50 border border-slate-200 text-[13.5px] outline-none focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100 transition-all"
            />
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              className="px-4 py-2.5 rounded-2xl bg-slate-50 border border-slate-200 text-[13.5px] text-slate-700 outline-none focus:border-indigo-300 focus:bg-white transition-all cursor-pointer"
            >
              {Object.keys(ROLE_COLORS).map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button
              onClick={commissionAgent}
              disabled={!form.name.trim() || commissioning}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-2xl bg-indigo-600 text-white text-[13px] font-bold hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              {commissioning ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              Commission
            </button>
            <input
              value={form.prompt}
              onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
              placeholder="Optional system prompt — shapes the agent's specialty"
              className="sm:col-span-3 px-4 py-2.5 rounded-2xl bg-slate-50 border border-slate-200 text-[13.5px] outline-none focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100 transition-all"
            />
            {formError && <p className="sm:col-span-3 text-[12px] text-rose-600">{formError}</p>}
          </div>
        )}
      </div>

      {/* Roster grid */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {roster.map((agent) => (
          <div
            key={agent.name}
            className="nxs-card rounded-3xl bg-white border border-slate-200/80 p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] hover:border-indigo-200"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <span
                  className="w-11 h-11 rounded-2xl flex items-center justify-center text-white text-[14px] font-extrabold shrink-0"
                  style={{ backgroundColor: roleColor(agent.role) }}
                >
                  {agent.name.slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0">
                  <p className="text-[14px] font-bold text-slate-900 truncate">{agent.name}</p>
                  <p className="text-[11px] nxs-mono mt-0.5" style={{ color: roleColor(agent.role) }}>
                    {agent.role}
                  </p>
                </div>
              </div>
              <span
                className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                  agent.status === 'idle' || agent.status === 'standby'
                    ? agent.live
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-slate-50 text-slate-500 border-slate-200'
                    : 'bg-cyan-50 text-cyan-700 border-cyan-200'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    agent.live ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
                  }`}
                />
                {agent.live ? 'live' : 'standby'}
              </span>
            </div>

            <p className="mt-3.5 text-[12.5px] leading-relaxed text-slate-500 line-clamp-2">{agent.specialty}</p>

            {agent.tools.length > 0 && (
              <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-400">
                <Wrench className="w-3 h-3" /> {agent.tools.slice(0, 3).join(' · ')}
                {agent.tools.length > 3 && <span>+{agent.tools.length - 3}</span>}
              </div>
            )}

            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span className="text-[10px] nxs-mono text-slate-300">
                {agent.live ? 'registered · tenant-scoped' : 'built-in enterprise roster'}
              </span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-300" />
            </div>
          </div>
        ))}
      </div>

      {/* Inter-agent bus (simulation) */}
      <div className="mt-4 rounded-3xl bg-[#0B0F19] border border-white/10 p-5 shadow-[0_20px_50px_-20px_rgba(11,15,25,0.6)]">
        <div className="flex items-center justify-between">
          <h4 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-indigo-300">
            <Radio className="w-3.5 h-3.5" /> Inter-agent message bus
          </h4>
          <span className="text-[10px] nxs-mono text-slate-500">simulation · mesh telemetry</span>
        </div>
        <div className="mt-3 space-y-1.5 max-h-36 overflow-hidden">
          {busMessages.map((m) => (
            <div key={m.id} className="flex items-center gap-2.5 text-[12px] nxs-mono nxs-bus-msg">
              <ArrowRight className="w-3 h-3 text-indigo-400 shrink-0" />
              <span className="text-slate-300 break-words">{m.text}</span>
            </div>
          ))}
        </div>
      </div>
    </ViewShell>
  );
};
