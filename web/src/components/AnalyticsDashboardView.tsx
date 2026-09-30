import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Cpu, 
  Database, 
  Activity, 
  Zap, 
  TrendingUp, 
  ShieldCheck, 
  Radio, 
  Server, 
  Eye, 
  CheckCircle2, 
  RefreshCw, 
  Download, 
  Filter,
  Layers,
  ArrowUpRight,
  Clock,
  HardDrive
} from 'lucide-react';
import { AgentStatus } from '../types';

interface AnalyticsDashboardViewProps {
  agentStatus: AgentStatus;
  onOpenClaudeStudio?: () => void;
  onOpenMultimodalBridge?: () => void;
}

export const AnalyticsDashboardView: React.FC<AnalyticsDashboardViewProps> = ({
  agentStatus,
  onOpenClaudeStudio,
  onOpenMultimodalBridge,
}) => {
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Live telemetry metrics
  const [metrics, setMetrics] = useState({
    cpuAvg: 42,
    memoryUsedGb: 5.4,
    vramUsedGb: 11.2,
    totalSynapses: 1420,
    networkThroughput: 1420,
    latencyMs: 14,
    activeAgents: 10,
    cacheHitRate: 99.4,
    astSecurityScore: 100,
    uptimeSeconds: 84320,
  });

  useEffect(() => {
    const timer = setInterval(() => {
      setMetrics((prev) => ({
        ...prev,
        cpuAvg: Math.min(88, Math.max(22, prev.cpuAvg + Math.floor(Math.random() * 9 - 4))),
        latencyMs: Math.min(24, Math.max(10, prev.latencyMs + Math.floor(Math.random() * 3 - 1))),
        networkThroughput: Math.min(2600, Math.max(800, prev.networkThroughput + Math.floor(Math.random() * 200 - 100))),
        uptimeSeconds: prev.uptimeSeconds + 1,
      }));
    }, 2000);
    return () => clearInterval(timer);
  }, [refreshTrigger]);

  const kpiCards = [
    {
      title: 'QUANTUM CORE LOAD',
      value: `${metrics.cpuAvg}%`,
      sub: 'Octa-Core Synthetic Load',
      change: '+2.4%',
      icon: Cpu,
      accent: 'cyan',
    },
    {
      title: 'GRAPH SYNAPSE DENSITY',
      value: `${metrics.totalSynapses.toLocaleString()}`,
      sub: 'Consolidated Memory Nodes',
      change: '+18 today',
      icon: Database,
      accent: 'emerald',
    },
    {
      title: 'NETWORK THROUGHPUT',
      value: `${metrics.networkThroughput} KB/s`,
      sub: `Latency: ${metrics.latencyMs}ms PING`,
      change: 'Zero Loss',
      icon: Radio,
      accent: 'purple',
    },
    {
      title: 'AST SECURITY INTEGRITY',
      value: `${metrics.astSecurityScore}%`,
      sub: 'Sandboxed Confinement',
      change: 'HARDENED',
      icon: ShieldCheck,
      accent: 'amber',
    },
  ];

  const agentSwarmData = [
    { name: 'Architect Agent', role: 'System Topology', status: 'ACTIVE', load: 38, successRate: '99.8%' },
    { name: 'Research Deep-Dive', role: 'Claim Synthesis', status: 'ACTIVE', load: 64, successRate: '99.4%' },
    { name: 'Code Sandbox Agent', role: 'AST Evaluation', status: 'ACTIVE', load: 52, successRate: '100%' },
    { name: 'Multimodal Transcoder', role: 'Spatial / OCR', status: 'READY', load: 24, successRate: '99.6%' },
    { name: 'Voice Cortex Core', role: 'Speech Synthesis', status: agentStatus === 'speaking' || agentStatus === 'listening' ? 'ACTIVE' : 'STANDBY', load: 45, successRate: '99.9%' },
    { name: 'Dream Consolidator', role: 'Subcortex Paging', status: 'ACTIVE', load: 30, successRate: '99.2%' },
  ];

  return (
    <div className="w-full h-full flex flex-col bg-[#0a0f1d] text-slate-100 font-mono overflow-y-auto select-none p-6 space-y-6">
      
      {/* ── Visual Pillar 1: Visual Hierarchy Header ─────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-[#00f0ff]/20">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-400/40 text-cyan-300 font-bold uppercase tracking-widest">
              WEB-BASED ANALYTICS VARIETY
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 font-bold uppercase">
              LIVE TELEMETRY SYNC
            </span>
          </div>
          <h1 className="text-xl font-black text-white tracking-widest uppercase flex items-center gap-2">
            <span>NEXUS OS — SYSTEMIC ANALYTICS DASHBOARD</span>
          </h1>
          <p className="text-xs text-slate-400 tracking-wide mt-0.5">
            Synchronized widescreen metrics, agent swarm throughput, and subcortex memory telemetry.
          </p>
        </div>

        {/* Dashboard Actions */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setRefreshTrigger((prev) => prev + 1)}
            className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 hover:border-cyan-400 text-xs text-slate-300 hover:text-white flex items-center gap-1.5 transition-all cursor-pointer active:scale-95"
          >
            <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
            <span>REFRESH</span>
          </button>

          <button
            onClick={onOpenMultimodalBridge}
            className="px-3 py-1.5 rounded-xl bg-cyan-950/90 hover:bg-cyan-900 border border-cyan-400/50 hover:border-cyan-300 text-xs font-bold text-cyan-200 flex items-center gap-1.5 transition-all cursor-pointer shadow-[0_0_15px_rgba(0,240,255,0.2)] active:scale-95"
          >
            <Eye className="w-3.5 h-3.5 text-cyan-400" />
            <span>MULTIMODAL BRIDGE</span>
          </button>
        </div>
      </div>

      {/* ── Visual Pillar 4: Scannable 4-Column KPI Matrix ───────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpiCards.map((kpi, idx) => {
          const Icon = kpi.icon;

          return (
            <div
              key={idx}
              className="p-4 rounded-2xl glass-obsidian border border-[#00f0ff]/20 hover:border-[#00f0ff]/50 transition-all duration-300 shadow-[0_4px_20px_rgba(0,0,0,0.5)] group hover:scale-101"
            >
              <div className="flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase tracking-widest mb-2">
                <span>{kpi.title}</span>
                <div className="p-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-cyan-400 group-hover:text-white transition-colors">
                  <Icon className="w-3.5 h-3.5" />
                </div>
              </div>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-2xl font-black text-white tracking-tight drop-shadow-[0_0_8px_rgba(0,240,255,0.3)]">
                  {kpi.value}
                </span>
                <span className="text-[10px] font-bold text-[#00ff88]">
                  {kpi.change}
                </span>
              </div>
              <p className="text-[10px] text-slate-500 font-medium truncate">
                {kpi.sub}
              </p>
            </div>
          );
        })}
      </div>

      {/* ── Synchronized Telemetry Data Graphs & Subcortex Metrics ───────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Area (7 cols): Throughput & Compute Load Area Chart */}
        <div className="lg:col-span-7 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.6)]">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                SYNCHRONIZED COMPUTE & MEMORY HISTOGRAM
              </span>
            </div>
            <span className="text-[9px] text-[#00ff88] font-bold">100% REAL-TIME NTP</span>
          </div>

          {/* Simulated SVG Waveform Graph */}
          <div className="relative h-44 w-full bg-[#040814]/80 rounded-2xl border border-slate-800/80 p-3 flex flex-col justify-between overflow-hidden">
            <div className="absolute inset-0 scanline pointer-events-none opacity-20" />
            <div className="flex items-center justify-between text-[8.5px] text-slate-500 z-10">
              <span>BANDWIDTH: PEAK 2.8 MB/s</span>
              <span>SYNAPSE DISPATCH RATE: 420 OPS/SEC</span>
            </div>

            {/* Sparkline Area */}
            <div className="h-28 w-full flex items-end gap-1.5 pt-2 z-10">
              {[28, 45, 62, 50, 78, 88, 65, 92, 70, 84, 96, 68, 74, 82, 90, 85, 94, 76, 88, 92].map((val, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end h-full">
                  <div 
                    className="w-full rounded-xs bg-gradient-to-t from-cyan-600 to-[#00ff88] hover:to-white transition-all duration-300"
                    style={{ height: `${val}%`, boxShadow: '0 0 6px rgba(0,240,255,0.4)' }}
                  />
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between text-[8px] text-slate-500 z-10">
              <span>T - 60 SEC</span>
              <span>T - 30 SEC</span>
              <span>LIVE [T - 0]</span>
            </div>
          </div>

          {/* Lower Hardware Specs Row */}
          <div className="grid grid-cols-3 gap-3 text-[10px]">
            <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
              <span className="text-slate-500 block text-[8.5px]">ALLOCATED RAM</span>
              <span className="text-cyan-300 font-bold">{metrics.memoryUsedGb} / 16.0 GB</span>
              <div className="w-full h-1 bg-slate-900 rounded-full mt-1.5 overflow-hidden">
                <div className="h-full bg-cyan-400 w-[34%]" />
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
              <span className="text-slate-500 block text-[8.5px]">GPU TENSOR VRAM</span>
              <span className="text-[#00ff88] font-bold">{metrics.vramUsedGb} / 24.0 GB</span>
              <div className="w-full h-1 bg-slate-900 rounded-full mt-1.5 overflow-hidden">
                <div className="h-full bg-[#00ff88] w-[46%]" />
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
              <span className="text-slate-500 block text-[8.5px]">SYSTEM UPTIME</span>
              <span className="text-amber-300 font-bold">{Math.floor(metrics.uptimeSeconds / 3600)}h {Math.floor((metrics.uptimeSeconds % 3600) / 60)}m</span>
              <div className="w-full h-1 bg-slate-900 rounded-full mt-1.5 overflow-hidden">
                <div className="h-full bg-amber-400 w-[100%]" />
              </div>
            </div>
          </div>
        </div>

        {/* Right Area (5 cols): Active Autonomous Agent Swarm Distribution */}
        <div className="lg:col-span-5 p-5 rounded-3xl glass-obsidian border border-[#00f0ff]/25 space-y-3.5 shadow-[0_8px_32px_rgba(0,0,0,0.6)]">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-bold text-white tracking-widest uppercase">
                NEURAL AGENT SWARM TELEMETRY
              </span>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-500/30 font-bold">
              10 NODES
            </span>
          </div>

          <div className="space-y-2 overflow-y-auto max-h-72 pr-1">
            {agentSwarmData.map((agent, i) => (
              <div 
                key={i}
                className="p-2.5 rounded-xl bg-[#040814]/70 border border-slate-800/80 hover:border-cyan-400/40 transition-colors flex items-center justify-between text-[10px]"
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
                    <span className="font-bold text-white">{agent.name}</span>
                  </div>
                  <span className="text-[8.5px] text-slate-500">{agent.role}</span>
                </div>

                <div className="text-right">
                  <span className="text-cyan-300 font-bold">{agent.successRate}</span>
                  <div className="w-16 h-1 bg-slate-900 rounded-full mt-1 overflow-hidden">
                    <div 
                      className="h-full bg-cyan-400"
                      style={{ width: `${agent.load}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={onOpenClaudeStudio}
            className="w-full py-2.5 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-300 hover:text-white font-bold text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-2 cursor-pointer active:scale-98"
          >
            <span>LAUNCH CLAUDE CODING STUDIO</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>

      </div>

    </div>
  );
};
