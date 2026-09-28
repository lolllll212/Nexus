import React from 'react';
import { 
  Cpu, 
  Search, 
  Layers, 
  Globe, 
  FolderKanban, 
  Zap, 
  Bot, 
  Database, 
  FileText, 
  Radio, 
  Activity, 
  CheckCircle2, 
  ShieldCheck,
  Code
} from 'lucide-react';
import { NodeCategory } from '../types';

interface LeftSidebarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  activeFilter: NodeCategory | null;
  onFilterChange: (cat: NodeCategory | null) => void;
  onOpenClaudeStudio: () => void;
  onOpenResearchMode: () => void;
  onOpenWorkflowMode: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  searchQuery,
  onSearchChange,
  activeFilter,
  onFilterChange,
  onOpenClaudeStudio,
  onOpenResearchMode,
  onOpenWorkflowMode,
}) => {
  const workspaces: { name: string; category?: NodeCategory; icon: any; count: number; action?: () => void }[] = [
    { name: 'Knowledge', category: 'CONCEPT', icon: Layers, count: 489 },
    { name: 'Research', category: 'RESEARCH', icon: Globe, count: 54, action: onOpenResearchMode },
    { name: 'Projects', category: 'PROJECT', icon: FolderKanban, count: 18 },
    { name: 'Workflows', category: 'WORKFLOW', icon: Zap, count: 24, action: onOpenWorkflowMode },
    { name: 'Agents', category: 'AGENT', icon: Bot, count: 6 },
    { name: 'Memory', category: 'MEMORY', icon: Database, count: 1420 },
    { name: 'Files', category: 'FILE', icon: FileText, count: 312 },
    { name: 'Integrations', category: 'API', icon: Radio, count: 14 },
  ];

  const recentActivities = [
    { title: 'Deep Research Ingestion', time: '2m ago', icon: Globe, color: 'text-cyan-400' },
    { title: 'Project Kernel Hardening', time: '14m ago', icon: ShieldCheck, color: 'text-emerald-400' },
    { title: 'GitHub Repository Scan', time: '32m ago', icon: Code, color: 'text-amber-400' },
    { title: 'Subcortex Memory Synced', time: '1h ago', icon: Database, color: 'text-purple-400' },
  ];

  return (
    <aside className="w-68 h-full border-r border-cyan-500/15 bg-slate-950/90 backdrop-blur-xl flex flex-col justify-between font-mono text-slate-300 shadow-2xl z-20">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="p-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5 mb-1">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-black font-bold shadow-[0_0_15px_rgba(0,240,255,0.4)]">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-xs font-bold text-white tracking-widest leading-none">
              NEXUS
            </h1>
            <span className="text-[8px] text-cyan-400 font-semibold tracking-wider">
              AUTONOMOUS COGNITIVE OS
            </span>
          </div>
        </div>

        {/* Brain Search */}
        <div className="mt-3 relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search the brain..."
            className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-[11px] text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-400/60 transition-colors"
          />
        </div>
      </div>

      {/* ── Navigation Workspaces ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-5">
        <div>
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-2 block mb-2">
            WORKSPACES
          </span>
          <div className="space-y-0.5">
            {workspaces.map((ws) => {
              const Icon = ws.icon;
              const isSelected = ws.category && activeFilter === ws.category;

              return (
                <button
                  key={ws.name}
                  onClick={() => {
                    if (ws.action) ws.action();
                    else if (ws.category) onFilterChange(isSelected ? null : ws.category);
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-400/40 shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-cyan-400' : 'text-slate-500'}`} />
                    <span>{ws.name}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {ws.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Recent Operational Activity Feed ──────────────────────────────── */}
        <div>
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-2 block mb-2 flex items-center gap-1.5">
            <Activity className="w-3 h-3 text-cyan-400" />
            <span>RECENT ACTIVITY</span>
          </span>
          <div className="space-y-1.5 px-1">
            {recentActivities.map((act, i) => {
              const ActIcon = act.icon;
              return (
                <div key={i} className="p-2 rounded-xl bg-slate-900/50 border border-slate-800/80 text-[10px]">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-slate-200 font-semibold truncate flex items-center gap-1.5">
                      <ActIcon className={`w-3 h-3 ${act.color}`} />
                      <span>{act.title}</span>
                    </span>
                    <span className="text-[9px] text-slate-500">{act.time}</span>
                  </div>
                  <div className="text-[9px] text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-2.5 h-2.5" />
                    <span>Checkpointed to Graph</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── System Status & Telemetry (Bottom) ──────────────────────────────── */}
      <div className="p-3.5 border-t border-slate-800 bg-slate-950/90 text-[10px] space-y-2">
        <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block">
          SYSTEM TELEMETRY
        </span>

        <div className="space-y-1 text-slate-400">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">CORTEX</span>
            <span className="text-emerald-400 font-bold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              ONLINE (14.2k t/s)
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-500">SUBCORTEX</span>
            <span className="text-purple-400 font-bold">ACTIVE (SYNTH)</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-500">AGENTS</span>
            <span className="text-cyan-300 font-bold">06 RUNNING</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-500">TOOLS</span>
            <span className="text-amber-400 font-bold">24 SANDBOXED</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-500">MEMORY</span>
            <span className="text-emerald-300 font-bold">SYNCED (99.8%)</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
