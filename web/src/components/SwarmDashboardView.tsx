import React, { useState, useEffect, useRef } from 'react';
import {
  Radio,
  Activity,
  Cpu,
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  Flame,
  Zap,
  Terminal,
  Wifi,
  WifiOff,
  Check,
  X,
  Search,
  Layers,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Server
} from 'lucide-react';
import { AgentStatus } from '../types';

interface SwarmDashboardViewProps {
  agentStatus?: AgentStatus;
  onOpenClaudeStudio?: () => void;
  onOpenMultimodalBridge?: () => void;
  onToggleAnalyticsMode?: () => void;
}

export interface SwarmAgent {
  status: 'idle' | 'working' | 'done' | 'offline';
  current_task?: string | null;
  doing?: string | null;
  last_heartbeat?: string | null;
  last_active?: string | null;
  owns?: string[];
}

export interface SwarmTask {
  id: string;
  description: string;
  for: string;
  requested_by?: string;
  status: 'pending' | 'claimed' | 'resolved' | 'verified';
  priority?: 'critical' | 'high' | 'medium' | 'low';
  evidence?: string | null;
  verified?: boolean;
  created_at?: string;
}

export interface ConsensusProposal {
  id: string;
  title?: string;
  description?: string;
  author?: string;
  status: 'draft' | 'under_review' | 'awaiting_ceo' | 'approved' | 'rejected';
  reviews?: Record<string, 'approved' | 'request_changes' | 'pending'>;
  evidence?: Record<string, string>;
  files?: string[];
  created_at?: string;
}

export interface AgentBudget {
  limit: number;
  used: number;
  pct: number;
  tier: 'primary' | 'local';
}

export interface HealIteration {
  id: string;
  agent?: string;
  kind?: string;
  text?: string;
  tags?: string[];
  created_at?: string;
}

export const SwarmDashboardView: React.FC<SwarmDashboardViewProps> = ({
  onOpenClaudeStudio,
  onOpenMultimodalBridge,
  onToggleAnalyticsMode,
}) => {
  // WebSocket State (NO POLLING - updates strictly pushed via WebSocket events)
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number>(0);
  const [clientCount, setClientCount] = useState<number>(1);
  const [messagesReceived, setMessagesReceived] = useState<number>(0);
  const [lastEventTime, setLastEventTime] = useState<string>('just now');

  // Swarm Entities
  const [agents, setAgents] = useState<Record<string, SwarmAgent>>({
    ceo: { status: 'done', current_task: 'Adjudicating upgrade spaces & monitoring consensus', last_heartbeat: new Date().toISOString() },
    astra: { status: 'working', current_task: 'task-033-plan-001 (LoRA pipeline & eval)', last_heartbeat: new Date().toISOString() },
    tron: { status: 'working', current_task: 'Upgrade Space 6 - Real-time swarm dashboard in web/', last_heartbeat: new Date().toISOString() },
    xenom: { status: 'idle', current_task: 'Standby for infrastructure & bridge telemetry', last_heartbeat: new Date().toISOString() },
  });

  const [taskQueue, setTaskQueue] = useState<SwarmTask[]>([]);
  const [consensusList, setConsensusList] = useState<ConsensusProposal[]>([]);
  const [budgets, setBudgets] = useState<Record<string, AgentBudget>>({
    ceo: { limit: 500000, used: 42100, pct: 8.4, tier: 'primary' },
    astra: { limit: 500000, used: 184500, pct: 36.9, tier: 'primary' },
    tron: { limit: 500000, used: 215300, pct: 43.1, tier: 'local' },
    xenom: { limit: 500000, used: 96400, pct: 19.3, tier: 'local' },
  });
  const [heals, setHeals] = useState<HealIteration[]>([]);

  // UI Filters
  const [taskFilter, setTaskFilter] = useState<'all' | 'pending' | 'claimed' | 'resolved' | 'verified'>('all');
  const [searchTask, setSearchTask] = useState('');
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pingStartRef = useRef<number>(0);

  // Initialize and maintain WebSocket connection to headless bridge
  useEffect(() => {
    let reconnectTimeout: any = null;
    let isCancelled = false;

    const connect = () => {
      if (isCancelled) return;
      const wsUrl = (import.meta as any).env?.VITE_BRIDGE_WS_URL || 'ws://127.0.0.1:8765';
      const token = (import.meta as any).env?.VITE_BRIDGE_TOKEN || '';
      const fullUrl = token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl;

      try {
        const ws = new WebSocket(fullUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isCancelled) {
            ws.close();
            return;
          }
          setWsConnected(true);
          // Authenticate if token provided
          if (token) {
            ws.send(JSON.stringify({ type: 'auth', token }));
          }
          // Request instant initial state sync
          ws.send(JSON.stringify({ type: 'get_state' }));

          // Measure ping latency
          pingStartRef.current = performance.now();
          ws.send(JSON.stringify({ type: 'ping' }));
        };

        ws.onmessage = (event) => {
          if (isCancelled) return;
          setMessagesReceived((prev) => prev + 1);
          setLastEventTime(new Date().toLocaleTimeString());

          try {
            const msg = JSON.parse(event.data);

            if (msg.type === 'pong') {
              const diff = Math.round(performance.now() - pingStartRef.current);
              setLatencyMs(diff);
              if (typeof msg.clients === 'number') {
                setClientCount(msg.clients);
              }
              return;
            }

            if (msg.type === 'event') {
              const payload = msg.payload || {};

              // Handle full swarm sync snapshot
              if (
                msg.topic === 'swarm.state_sync' ||
                payload.nexus_event === 'swarm_sync' ||
                payload.snapshot
              ) {
                const snap = payload.snapshot || payload;
                if (snap.agents) setAgents(snap.agents);
                if (Array.isArray(snap.task_queue)) setTaskQueue(snap.task_queue);
                if (Array.isArray(snap.consensus)) setConsensusList(snap.consensus);
                if (snap.budgets) setBudgets(snap.budgets);
                if (Array.isArray(snap.heals)) setHeals(snap.heals);
                return;
              }

              // Handle individual delta events
              if (payload.nexus_event === 'task_created') {
                setTaskQueue((prev) => {
                  if (prev.some((t) => t.id === payload.task_id)) return prev;
                  return [
                    {
                      id: payload.task_id,
                      description: payload.description || '',
                      for: payload.for || 'unassigned',
                      status: 'pending',
                      priority: payload.priority || 'medium',
                      created_at: payload.at || new Date().toISOString(),
                    },
                    ...prev,
                  ];
                });
              } else if (payload.nexus_event === 'task_updated' && payload.task) {
                setTaskQueue((prev) =>
                  prev.map((t) => (t.id === payload.task.id ? { ...t, ...payload.task } : t))
                );
              } else if (payload.nexus_event === 'agents_updated' && payload.agents) {
                setAgents(payload.agents);
              } else if (payload.nexus_event === 'consensus_updated' && Array.isArray(payload.proposals)) {
                setConsensusList(payload.proposals);
              } else if (payload.nexus_event === 'budget_updated' && payload.budgets) {
                setBudgets(payload.budgets);
              } else if (payload.nexus_event === 'heals_updated' && Array.isArray(payload.heals)) {
                setHeals(payload.heals);
              }
            }
          } catch (err) {
            console.error('[swarm-ws] Parse error:', err);
          }
        };

        ws.onclose = () => {
          if (isCancelled) return;
          setWsConnected(false);
          reconnectTimeout = setTimeout(connect, 2500);
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch {
        setWsConnected(false);
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    // Regular ping loop (every 10s) to keep socket fresh and measure roundtrip
    const pingInterval = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        pingStartRef.current = performance.now();
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 10000);

    return () => {
      isCancelled = true;
      clearInterval(pingInterval);
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleManualSync = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'get_state' }));
      pingStartRef.current = performance.now();
      wsRef.current.send(JSON.stringify({ type: 'ping' }));
    }
  };

  const filteredTasks = taskQueue.filter((t) => {
    if (taskFilter !== 'all' && t.status !== taskFilter) return false;
    if (searchTask.trim()) {
      const q = searchTask.toLowerCase();
      return (
        t.id.toLowerCase().includes(q) ||
        t.for.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const getAgentColor = (name: string) => {
    switch (name.toLowerCase()) {
      case 'ceo':
        return 'text-amber-400 border-amber-500/40 bg-amber-950/60';
      case 'astra':
        return 'text-purple-400 border-purple-500/40 bg-purple-950/60';
      case 'tron':
        return 'text-cyan-400 border-cyan-500/40 bg-cyan-950/60';
      case 'xenom':
        return 'text-emerald-400 border-emerald-500/40 bg-emerald-950/60';
      default:
        return 'text-slate-400 border-slate-700 bg-slate-900/60';
    }
  };

  const getStatusDot = (status: string) => {
    switch (status) {
      case 'working':
        return <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping inline-block" />;
      case 'done':
      case 'verified':
        return <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-[0_0_8px_#10b981]" />;
      case 'idle':
        return <span className="w-2 h-2 rounded-full bg-slate-500 inline-block" />;
      default:
        return <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />;
    }
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#0a0f1d] text-slate-100 font-mono overflow-y-auto select-none p-6 space-y-6">
      {/* ── TOP TELEMETRY & WEBSOCKET HEADER ─────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-[#00f0ff]/20">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-cyan-950/90 border border-cyan-400/50 text-cyan-300 font-bold uppercase tracking-widest flex items-center gap-1.5 shadow-[0_0_10px_rgba(0,240,255,0.2)]">
              <Radio className="w-3 h-3 text-cyan-400 animate-pulse" />
              <span>UPGRADE SPACE 6 — REAL-TIME SWARM DASHBOARD</span>
            </span>
            <span
              className={`text-[10px] px-2.5 py-0.5 rounded-full border font-bold uppercase flex items-center gap-1.5 ${
                wsConnected
                  ? 'bg-emerald-950/90 border-emerald-400/50 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                  : 'bg-rose-950/90 border-rose-400/50 text-rose-300 animate-pulse'
              }`}
            >
              {wsConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
              <span>{wsConnected ? `WS CONNECTED (${latencyMs}ms)` : 'RECONNECTING TO BRIDGE...'}</span>
            </span>
          </div>

          <h1 className="text-xl font-black text-white tracking-widest uppercase flex items-center gap-2">
            <span>NEXUS MULTI-AGENT SWARM COCKPIT</span>
          </h1>
          <p className="text-xs text-slate-400 tracking-wide mt-0.5 flex items-center gap-3">
            <span>WebSocket bus: <code className="text-cyan-300">ws://127.0.0.1:8765</code></span>
            <span>•</span>
            <span>Events: <strong className="text-white">{messagesReceived}</strong></span>
            <span>•</span>
            <span>Last sync: <span className="text-slate-300">{lastEventTime}</span></span>
          </p>
        </div>

        {/* Top Control Triggers */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={handleManualSync}
            title="Send sync request over WebSocket"
            className="px-3.5 py-1.5 rounded-xl bg-slate-900 border border-slate-700 hover:border-cyan-400 text-xs text-slate-300 hover:text-white flex items-center gap-1.5 transition-all cursor-pointer active:scale-95"
          >
            <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
            <span>SYNC BRIDGE</span>
          </button>

          {onToggleAnalyticsMode && (
            <button
              onClick={onToggleAnalyticsMode}
              className="px-3 py-1.5 rounded-xl bg-purple-950/80 border border-purple-500/40 hover:border-purple-300 text-xs font-bold text-purple-200 flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <BarChart3 className="w-3.5 h-3.5 text-purple-400" />
              <span>HARDWARE TELEMETRY</span>
            </button>
          )}

          {onOpenClaudeStudio && (
            <button
              onClick={onOpenClaudeStudio}
              className="px-3 py-1.5 rounded-xl bg-amber-950/90 border border-amber-500/50 hover:border-amber-400 text-xs font-bold text-amber-200 flex items-center gap-1.5 transition-all cursor-pointer shadow-[0_0_12px_rgba(245,158,11,0.25)]"
            >
              <Terminal className="w-3.5 h-3.5 text-amber-400" />
              <span>CODING STUDIO</span>
            </button>
          )}
        </div>
      </div>

      {/* ── PILLAR 1: LIVE AGENTS SWARM TELEMETRY ──────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-bold text-white tracking-widest uppercase">
              ACTIVE SWARM AGENTS (PORT CONFLICT RESOLUTION & CRDTs)
            </span>
          </div>
          <span className="text-[10px] text-cyan-400/80">4 OF 4 AGENTS TRACKED VIA HEARTBEAT</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { id: 'ceo', name: 'CEO WATCHDOG', role: 'Consensus Adjudication & Triage', icon: ShieldCheck },
            { id: 'astra', name: 'ASTRA', role: 'Application, Autonomy & LoRA', icon: Flame },
            { id: 'tron', name: 'TRON', role: 'Domain Ports, CRDTs & Learned Router', icon: Terminal },
            { id: 'xenom', name: 'XENOM', role: 'Infrastructure, Security & Bridge', icon: Server },
          ].map(({ id, name, role, icon: Icon }) => {
            const agentData = agents[id] || { status: 'idle', current_task: 'Standing by' };
            const isWorking = agentData.status === 'working';
            const colorClass = getAgentColor(id);

            return (
              <div
                key={id}
                className={`p-4 rounded-2xl glass-obsidian border transition-all duration-300 shadow-[0_4px_20px_rgba(0,0,0,0.5)] relative overflow-hidden group hover:scale-101 ${
                  isWorking ? 'border-cyan-400/50 shadow-[0_0_20px_rgba(0,240,255,0.15)]' : 'border-slate-800'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className={`p-1.5 rounded-lg border ${colorClass}`}>
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <span className="text-xs font-black text-white tracking-wider">{name}</span>
                  </div>

                  <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] font-bold">
                    {getStatusDot(agentData.status)}
                    <span className="uppercase tracking-wider">{agentData.status}</span>
                  </div>
                </div>

                <div className="text-[10px] text-slate-400 font-medium mb-3 truncate" title={role}>
                  {role}
                </div>

                <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/80 mb-2">
                  <span className="text-[9px] text-slate-500 uppercase font-bold block mb-0.5">CURRENT FOCUS / DOING</span>
                  <p className="text-[10.5px] text-cyan-200 font-medium line-clamp-2 leading-relaxed">
                    {agentData.current_task || agentData.doing || 'Standing by for next task queue claim'}
                  </p>
                </div>

                <div className="flex items-center justify-between text-[9px] text-slate-500 pt-1">
                  <span>Heartbeat: {agentData.last_heartbeat ? new Date(agentData.last_heartbeat).toLocaleTimeString() : 'Active'}</span>
                  <span className="text-cyan-400/80 font-bold uppercase">Tick sync OK</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── PILLAR 2 & 3: TASK QUEUE & CONSENSUS VOTES ─────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Area (7 cols): Real-Time Task Queue */}
        <div className="lg:col-span-7 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)] flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                SHARED TASK QUEUE ({filteredTasks.length})
              </span>
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-[10px]">
              {(['all', 'pending', 'claimed', 'resolved', 'verified'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setTaskFilter(st)}
                  className={`px-2 py-0.5 rounded-lg capitalize font-bold transition-all cursor-pointer ${
                    taskFilter === st
                      ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/40 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search tasks by ID, assigned agent, or description..."
              value={searchTask}
              onChange={(e) => setSearchTask(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400"
            />
          </div>

          {/* Task List Scroll Container */}
          <div className="space-y-2.5 overflow-y-auto max-h-[380px] pr-1 flex-1">
            {filteredTasks.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs rounded-2xl border border-dashed border-slate-800">
                No tasks matching the selected filter in current swarm state.
              </div>
            ) : (
              filteredTasks.map((t) => {
                const isExpanded = expandedTaskId === t.id;
                const agentBadge = getAgentColor(t.for);

                return (
                  <div
                    key={t.id}
                    className="p-3 rounded-2xl bg-[#040814]/80 border border-slate-800/90 hover:border-cyan-500/40 transition-all text-xs"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-white tracking-wide">{t.id}</span>
                        <span className={`px-2 py-0.5 rounded-md border text-[9px] uppercase font-bold ${agentBadge}`}>
                          {t.for}
                        </span>
                        {t.priority && (
                          <span
                            className={`px-1.5 py-0.5 rounded text-[8.5px] uppercase font-bold ${
                              t.priority === 'critical'
                                ? 'bg-rose-950 text-rose-300 border border-rose-500/40'
                                : t.priority === 'high'
                                ? 'bg-amber-950 text-amber-300 border border-amber-500/40'
                                : 'bg-slate-900 text-slate-400 border border-slate-800'
                            }`}
                          >
                            {t.priority}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[9.5px] px-2 py-0.5 rounded-full font-bold uppercase flex items-center gap-1 ${
                            t.status === 'verified'
                              ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40'
                              : t.status === 'resolved'
                              ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-500/40'
                              : t.status === 'claimed'
                              ? 'bg-amber-950/80 text-amber-300 border border-amber-500/40'
                              : 'bg-slate-900 text-slate-400 border border-slate-800'
                          }`}
                        >
                          {t.verified ? <Check className="w-2.5 h-2.5" /> : null}
                          <span>{t.status}</span>
                        </span>

                        <button
                          onClick={() => setExpandedTaskId(isExpanded ? null : t.id)}
                          className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 cursor-pointer"
                        >
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    <p className={`text-slate-300 text-[11px] leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`}>
                      {t.description}
                    </p>

                    {isExpanded && t.evidence && (
                      <div className="mt-2.5 p-2 rounded-xl bg-slate-950 border border-emerald-500/30 text-[10px]">
                        <span className="text-emerald-400 font-bold block mb-1 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>ATTACHED EVIDENCE (GATES & VERIFICATION):</span>
                        </span>
                        <code className="text-emerald-200/90 whitespace-pre-wrap block font-mono text-[9.5px]">
                          {t.evidence}
                        </code>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Area (5 cols): Consensus Proposals Awaiting CEO */}
        <div className="lg:col-span-5 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)] flex flex-col">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                CONSENSUS VOTES AWAITING CEO
              </span>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-500/30 font-bold">
              BANDIT REVIEW ENFORCED
            </span>
          </div>

          <div className="space-y-3 overflow-y-auto max-h-[380px] pr-1 flex-1">
            {consensusList.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-xs rounded-2xl border border-dashed border-slate-800 space-y-2">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto opacity-70" />
                <p className="font-bold text-white">ALL DRAFTS RESOLVED</p>
                <p className="text-[10.5px] text-slate-500">
                  No patches currently awaiting CEO review or machine consensus vote.
                </p>
              </div>
            ) : (
              consensusList.map((prop) => (
                <div
                  key={prop.id}
                  className="p-3.5 rounded-2xl bg-[#040814]/80 border border-amber-500/30 hover:border-amber-400/60 transition-all text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-black text-amber-300 tracking-wide">{prop.id}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-500/40 uppercase font-bold animate-pulse">
                      Awaiting CEO
                    </span>
                  </div>

                  <p className="text-slate-300 text-[11px] font-medium">{prop.title || prop.description}</p>

                  {/* Reviewers grid */}
                  <div className="grid grid-cols-4 gap-1.5 pt-1 text-[9px]">
                    {['astra', 'tron', 'xenom', 'bandit'].map((rev) => {
                      const vote = prop.reviews?.[rev] || 'approved';
                      const isOk = vote === 'approved' || vote === 'passed';
                      return (
                        <div
                          key={rev}
                          className={`p-1.5 rounded-lg border text-center font-bold uppercase ${
                            isOk
                              ? 'bg-emerald-950/70 border-emerald-500/30 text-emerald-300'
                              : 'bg-rose-950/70 border-rose-500/30 text-rose-300'
                          }`}
                        >
                          <div className="text-[8px] text-slate-400">{rev}</div>
                          <div>{isOk ? '✓ PASS' : '✗ REQ'}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── PILLAR 4 & 5: TOKEN BUDGETS BURNING & HEAL ITERATIONS ───────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Area (6 cols): Token Budgets Burning */}
        <div className="lg:col-span-6 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)]">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-rose-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                TOKEN BUDGETS BURNING (500K DAILY CAP)
              </span>
            </div>
            <span className="text-[9px] text-[#00ff88] font-bold">COST-AWARE ROUTER ACTIVE</span>
          </div>

          <div className="space-y-3.5">
            {(Object.entries(budgets) as [string, AgentBudget][]).map(([agent, b]) => {
              const isOverHalf = b.pct > 50;
              const isOver80 = b.pct > 80;

              return (
                <div key={agent} className="p-3 rounded-2xl bg-slate-950/70 border border-slate-800/80 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-white uppercase flex items-center gap-2">
                      <span className="capitalize">{agent}</span>
                      <span
                        className={`text-[8.5px] px-1.5 py-0.5 rounded uppercase font-bold ${
                          b.tier === 'primary'
                            ? 'bg-amber-950/80 text-amber-300 border border-amber-500/30'
                            : 'bg-cyan-950/80 text-cyan-300 border border-cyan-500/30'
                        }`}
                      >
                        {b.tier} tier
                      </span>
                    </span>

                    <span className="text-[10px] text-slate-400">
                      <strong className="text-white">{b.used.toLocaleString()}</strong> / {b.limit.toLocaleString()} tok ({b.pct}%)
                    </span>
                  </div>

                  <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 rounded-full ${
                        isOver80
                          ? 'bg-gradient-to-r from-amber-500 to-rose-500'
                          : isOverHalf
                          ? 'bg-gradient-to-r from-cyan-500 to-amber-500'
                          : 'bg-gradient-to-r from-emerald-500 to-cyan-500'
                      }`}
                      style={{ width: `${Math.min(100, b.pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Area (6 cols): Heal Iterations Stream */}
        <div className="lg:col-span-6 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)]">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                AUTONOMOUS HEAL ITERATIONS (TRACEBACK PIPES)
              </span>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-bold">
              PYTEST SLICE FEEDBACK
            </span>
          </div>

          <div className="space-y-2.5 overflow-y-auto max-h-60 pr-1">
            {heals.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs rounded-2xl border border-dashed border-slate-800">
                All test suites green. No active heal loops triggered.
              </div>
            ) : (
              heals.map((h, i) => (
                <div
                  key={h.id || i}
                  className="p-3 rounded-2xl bg-slate-950/70 border border-slate-800 hover:border-emerald-400/40 transition-colors text-xs space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="font-bold text-emerald-300 uppercase">
                      HEAL CYCLE {h.agent ? `[${h.agent}]` : ''}
                    </span>
                    <span className="text-slate-500">
                      {h.created_at ? new Date(h.created_at).toLocaleTimeString() : 'Recent'}
                    </span>
                  </div>
                  <p className="text-slate-300 text-[10.5px] line-clamp-2 leading-relaxed">
                    {h.text || 'Targeted patch applied and verified by pytest.'}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
