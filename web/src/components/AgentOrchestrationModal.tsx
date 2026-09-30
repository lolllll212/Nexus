import React, { useState, useEffect } from 'react';
import { 
  AutonomousAgent, 
  InterAgentMessage 
} from '../types';
import { 
  AUTONOMOUS_AGENTS, 
  INITIAL_INTER_AGENT_MESSAGES 
} from '../data/nexusGraphData';
import { 
  X, 
  Bot, 
  Zap, 
  Activity, 
  Cpu, 
  Terminal, 
  Radio, 
  Send, 
  CheckCircle2, 
  Clock, 
  Layers, 
  Pause, 
  Play, 
  Search, 
  Eye, 
  FileCode, 
  BarChart3, 
  PenTool, 
  ShieldCheck, 
  Database, 
  ArrowRight,
  Sparkles
} from 'lucide-react';
import { playHudClick } from '../utils/soundEffects';

interface AgentOrchestrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenClaudeStudio: () => void;
  onOpenResearchMode: (topic?: string) => void;
}

const ROLE_ICONS: Record<AutonomousAgent['role'], any> = {
  Researcher: Search,
  Coder: FileCode,
  Planner: Layers,
  Browser: Radio,
  Vision: Eye,
  'Data Analyst': BarChart3,
  Writer: PenTool,
  Executor: Terminal,
  Memory: Database,
  'Fact Checker': ShieldCheck,
};

export const AgentOrchestrationModal: React.FC<AgentOrchestrationModalProps> = ({
  isOpen,
  onClose,
  onOpenClaudeStudio,
  onOpenResearchMode,
}) => {
  const [agents, setAgents] = useState<AutonomousAgent[]>(AUTONOMOUS_AGENTS);
  const [messages, setMessages] = useState<InterAgentMessage[]>(INITIAL_INTER_AGENT_MESSAGES);
  const [selectedAgent, setSelectedAgent] = useState<AutonomousAgent | null>(agents[0]);
  const [isSwarmActive, setIsSwarmActive] = useState(true);
  const [broadcastInput, setBroadcastInput] = useState('');

  // Periodically generate simulated inter-agent communication messages
  useEffect(() => {
    if (!isOpen || !isSwarmActive) return;

    const interval = setInterval(() => {
      const handoffs = [
        { from: 'Researcher', to: 'Fact Checker', type: 'VERIFICATION_REQUEST' as const, content: 'Discovered arXiv:2409.1120. Cross-checking claims against peer-reviewed citations.' },
        { from: 'Fact Checker', to: 'Planner', type: 'DATA_PAYLOAD' as const, content: 'Contradiction score resolved (0.04). Safe for DAG dependency insertion.' },
        { from: 'Planner', to: 'Coder', type: 'TASK_HANDOFF' as const, content: 'Assigned code synthesis task: Implement SSRF guard with CIDR IP range validator.' },
        { from: 'Coder', to: 'Executor', type: 'AST_ARTIFACT' as const, content: 'Generated ssrf.py with strict IP blocking. Executing in Docker sandbox container.' },
        { from: 'Executor', to: 'Memory', type: 'SYNAPSE_SIGNAL' as const, content: 'Test suite passed (14/14 tests). Writing memory vectors to Qdrant subcortex.' },
        { from: 'Memory', to: 'Writer', type: 'DATA_PAYLOAD' as const, content: 'Updated knowledge graph synapses. Synthesizing executive deployment brief.' },
      ];

      const sample = handoffs[Math.floor(Math.random() * handoffs.length)];
      const now = new Date().toTimeString().split(' ')[0];
      const newMsg: InterAgentMessage = {
        id: `msg-${Date.now()}`,
        timestamp: now,
        fromAgent: sample.from,
        toAgent: sample.to,
        type: sample.type,
        content: sample.content,
        status: 'delivered',
      };

      setMessages((prev) => [newMsg, ...prev.slice(0, 15)]);

      // Dynamically bump progress for active agents
      setAgents((prev) =>
        prev.map((ag) => {
          if (ag.role === sample.from || ag.role === sample.to) {
            const nextProgress = Math.min(100, (ag.progress + 6) % 100 || 85);
            return {
              ...ag,
              progress: nextProgress,
              latency: Math.floor(14 + Math.random() * 25),
            };
          }
          return ag;
        })
      );
    }, 4500);

    return () => clearInterval(interval);
  }, [isOpen, isSwarmActive]);

  if (!isOpen) return null;

  const handleBroadcastTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!broadcastInput.trim()) return;

    const now = new Date().toTimeString().split(' ')[0];
    const newMsg: InterAgentMessage = {
      id: `broadcast-${Date.now()}`,
      timestamp: now,
      fromAgent: 'Operator',
      toAgent: 'Planner',
      type: 'TASK_HANDOFF',
      content: `Dispatched swarm directive: "${broadcastInput}"`,
      status: 'processing',
    };

    setMessages((prev) => [newMsg, ...prev]);
    setBroadcastInput('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-xl font-mono text-slate-100 select-none animate-fadeIn">
      <div className="w-full max-w-7xl h-[92vh] rounded-3xl glass-panel border border-cyan-500/30 bg-slate-950/95 flex flex-col overflow-hidden shadow-[0_20px_60px_rgba(0,0,0,0.9),0_0_30px_rgba(0,240,255,0.15)]">
        {/* ── Top Modal Header ────────────────────────────────────────────── */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-purple-600 flex items-center justify-center text-black font-bold shadow-[0_0_20px_rgba(0,240,255,0.4)]">
              <Bot className="w-5 h-5 text-slate-950" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold tracking-wider text-white">
                  AUTONOMOUS AGENT ORCHESTRATION LAYER
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-cyan-950/80 border border-cyan-400/40 text-cyan-300">
                  10 ENTERPRISE AGENTS
                </span>
                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-950/80 border border-emerald-400/40 text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  SWARM ACTIVE
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">
                Real-time multi-agent ReAct loop &bull; Inter-agent message bus &bull; AST guard execution &bull; Subcortex memory consolidation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Swarm State Toggle */}
            <button
              onClick={() => {
                setIsSwarmActive(!isSwarmActive);
                playHudClick();
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                isSwarmActive
                  ? 'bg-amber-950/40 border-amber-500/40 text-amber-300 hover:bg-amber-950/70'
                  : 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300 hover:bg-emerald-950/70'
              }`}
            >
              {isSwarmActive ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              <span>{isSwarmActive ? 'Freeze Swarm' : 'Resume Swarm'}</span>
            </button>

            {/* Launch Claude Studio */}
            <button
              onClick={() => {
                onClose();
                onOpenClaudeStudio();
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-950/60 border border-amber-500/40 text-amber-300 hover:bg-amber-900/60 transition-all cursor-pointer"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Claude Studio</span>
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── Main Workspace Body ──────────────────────────────────────────── */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Grid: 10 Autonomous Agents */}
          <div className="flex-1 p-5 overflow-y-auto space-y-4 border-r border-slate-800/80">
            <div className="flex items-center justify-between pb-1">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                <span>Autonomous Agents Universe (10 Active Units)</span>
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                Aggregate Throughput: ~1,020 t/s &bull; Avg Latency: 24.8ms
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {agents.map((ag) => {
                const Icon = ROLE_ICONS[ag.role] || Bot;
                const isSelected = selectedAgent?.id === ag.id;

                return (
                  <div
                    key={ag.id}
                    onClick={() => {
                      setSelectedAgent(ag);
                      playHudClick();
                    }}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer relative overflow-hidden ${
                      isSelected
                        ? 'bg-slate-900/90 border-cyan-400/60 shadow-[0_0_20px_rgba(0,240,255,0.2)]'
                        : 'bg-slate-950/70 hover:bg-slate-900/50 border-slate-800/80 hover:border-slate-700'
                    }`}
                  >
                    {/* Top row: Role, Icon, Status pill */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2.5">
                        <div
                          className="w-8 h-8 rounded-xl flex items-center justify-center font-bold"
                          style={{
                            backgroundColor: `${ag.avatarColor}20`,
                            color: ag.avatarColor,
                            border: `1px solid ${ag.avatarColor}50`,
                          }}
                        >
                          <Icon className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="text-xs font-bold text-white leading-tight">
                            {ag.name}
                          </h3>
                          <span className="text-[9px] text-slate-400 font-mono">
                            {ag.model}
                          </span>
                        </div>
                      </div>

                      <span
                        className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
                          ag.status === 'executing'
                            ? 'bg-cyan-950/80 border border-cyan-400/40 text-cyan-300 animate-pulse'
                            : ag.status === 'thinking'
                            ? 'bg-purple-950/80 border border-purple-400/40 text-purple-300'
                            : ag.status === 'active'
                            ? 'bg-emerald-950/80 border border-emerald-400/40 text-emerald-300'
                            : 'bg-slate-900 border border-slate-700 text-slate-400'
                        }`}
                      >
                        {ag.status}
                      </span>
                    </div>

                    {/* Current Task */}
                    <p className="text-[11px] text-slate-300 line-clamp-2 mb-2.5 leading-snug">
                      {ag.task}
                    </p>

                    {/* Tools array */}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {ag.tools.map((t) => (
                        <span
                          key={t}
                          className="px-1.5 py-0.2 rounded text-[8px] bg-slate-900/90 text-slate-400 border border-slate-800"
                        >
                          {t}
                        </span>
                      ))}
                    </div>

                    {/* Progress Bar & Telemetry Metrics */}
                    <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
                      <div className="flex items-center justify-between text-[9px] text-slate-400">
                        <span className="flex items-center gap-1">
                          <Activity className="w-3 h-3 text-cyan-400" />
                          <span>{ag.tokens}</span>
                        </span>
                        <span>{ag.latency}ms latency</span>
                        <span className="text-cyan-300 font-bold">{ag.progress}%</span>
                      </div>

                      <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-cyan-500 to-blue-500"
                          style={{ width: `${ag.progress}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Panel: Inter-Agent Live Message Stream & Inspector */}
          <div className="w-96 flex flex-col bg-slate-950/90 border-l border-slate-800">
            {/* Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <span className="text-[11px] font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Radio className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
                <span>Inter-Agent Communication Bus</span>
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded bg-purple-950/70 border border-purple-500/30 text-purple-300 font-bold">
                LIVE SSE
              </span>
            </div>

            {/* Live Message Feed */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className="p-2.5 rounded-xl bg-slate-900/70 border border-slate-800 text-[10px] space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="text-cyan-400">{m.fromAgent}</span>
                      <ArrowRight className="w-2.5 h-2.5 text-slate-500" />
                      <span className="text-purple-400">{m.toAgent}</span>
                    </div>
                    <span className="text-[9px] text-slate-500">{m.timestamp}</span>
                  </div>

                  <span className="inline-block px-1.5 py-0.2 rounded text-[8px] font-bold bg-slate-950 border border-slate-700 text-amber-400">
                    {m.type}
                  </span>

                  <p className="text-slate-300 text-[10px] leading-relaxed">
                    {m.content}
                  </p>
                </div>
              ))}
            </div>

            {/* Broadcast Terminal Input */}
            <form onSubmit={handleBroadcastTask} className="p-3 border-t border-slate-800 bg-slate-900/40">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={broadcastInput}
                  onChange={(e) => setBroadcastInput(e.target.value)}
                  placeholder="Broadcast directive to Swarm Planner..."
                  className="flex-1 bg-slate-950 px-3 py-2 rounded-xl border border-slate-800 text-[11px] text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-400/50"
                />
                <button
                  type="submit"
                  disabled={!broadcastInput.trim()}
                  className="p-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold disabled:opacity-40 transition-all cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
