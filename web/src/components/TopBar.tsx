import React from 'react';
import { 
  OperatingMode 
} from '../types';
import { 
  Share2, 
  Search, 
  Zap, 
  Cpu, 
  Terminal, 
  Maximize2, 
  Minimize2, 
  Bell, 
  Settings, 
  User, 
  Activity,
  Layers,
  Sparkles,
  Command,
  Mic,
  ShieldCheck
} from 'lucide-react';

interface TopBarProps {
  currentMode: OperatingMode;
  onModeChange: (mode: OperatingMode) => void;
  onOpenClaudeStudio: () => void;
  onToggleFullscreen: () => void;
  isFullscreen: boolean;
  onOpenCommandCenter: () => void;
  onOpenVoiceCortex: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  currentMode,
  onModeChange,
  onOpenClaudeStudio,
  onToggleFullscreen,
  isFullscreen,
  onOpenCommandCenter,
  onOpenVoiceCortex,
}) => {
  const modes: { id: OperatingMode; label: string; icon: any }[] = [
    { id: 'GRAPH', label: 'GRAPH', icon: Share2 },
    { id: 'RESEARCH', label: 'RESEARCH', icon: Search },
    { id: 'WORKFLOW', label: 'WORKFLOW', icon: Zap },
    { id: 'ARCHITECTURE', label: 'ARCHITECTURE', icon: Cpu },
  ];

  return (
    <header className="fixed top-3 left-1/2 -translate-x-1/2 z-30 flex items-center justify-between gap-4 px-4 py-2 rounded-2xl glass-panel border border-cyan-500/25 bg-slate-950/85 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.7),0_0_20px_rgba(0,240,255,0.15)] select-none w-[94vw] max-w-7xl font-mono">
      {/* ── Left Quick Triggers ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-white tracking-widest px-2 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-400/40 text-cyan-400 flex items-center gap-1.5 shadow-[0_0_10px_rgba(0,240,255,0.3)]">
          <Cpu className="w-3.5 h-3.5" />
          <span>NEXUS</span>
        </span>

        <div className="hidden lg:flex items-center gap-1 text-[11px] text-slate-400">
          <button
            onClick={() => onModeChange('GRAPH')}
            className={`px-2.5 py-1 rounded-xl transition-colors cursor-pointer ${
              currentMode === 'GRAPH' ? 'text-cyan-300 font-bold bg-cyan-950/50' : 'hover:text-slate-200'
            }`}
          >
            WORKSHOP
          </button>
          <button
            onClick={() => onModeChange('RESEARCH')}
            className={`px-2.5 py-1 rounded-xl transition-colors cursor-pointer ${
              currentMode === 'RESEARCH' ? 'text-cyan-300 font-bold bg-cyan-950/50' : 'hover:text-slate-200'
            }`}
          >
            RESEARCH
          </button>
          <button
            onClick={() => onModeChange('WORKFLOW')}
            className={`px-2.5 py-1 rounded-xl transition-colors cursor-pointer ${
              currentMode === 'WORKFLOW' ? 'text-cyan-300 font-bold bg-cyan-950/50' : 'hover:text-slate-200'
            }`}
          >
            WORKFLOWS
          </button>
        </div>

        {/* Dedicated Claude Coding Studio Launcher */}
        <button
          onClick={onOpenClaudeStudio}
          className="flex items-center gap-1.5 px-3 py-1 rounded-xl text-[11px] font-bold text-amber-300 bg-amber-950/70 hover:bg-amber-900 border border-amber-500/50 transition-all shadow-[0_0_10px_rgba(245,158,11,0.25)] cursor-pointer"
          title="Open Claude Coding Studio (Hotkey: C)"
        >
          <Terminal className="w-3.5 h-3.5 text-amber-400" />
          <span>Claude Studio</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-amber-900/80 text-amber-200 ml-1">C</span>
        </button>
      </div>

      {/* ── Center Live Operating Mode Selector ─────────────────────────────── */}
      <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-900/90 border border-slate-800 shadow-inner">
        {modes.map((m) => {
          const Icon = m.icon;
          const isActive = currentMode === m.id;

          return (
            <button
              key={m.id}
              onClick={() => onModeChange(m.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
              <span>{m.label}</span>
            </button>
          );
        })}
      </div>

      {/* ── Right Telemetry & Actions ───────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-[10px] text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.9)]"></span>
          <span>SYSTEM ONLINE</span>
        </div>

        {/* Voice Cortex Assistant Trigger */}
        <button
          onClick={onOpenVoiceCortex}
          className="p-1.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
          title="Voice Cortex"
        >
          <Mic className="w-4 h-4" />
        </button>

        {/* Command Center Palette Trigger */}
        <button
          onClick={onOpenCommandCenter}
          className="p-1.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
          title="Command Palette (Ctrl+K)"
        >
          <Command className="w-4 h-4" />
        </button>

        {/* Fullscreen Toggle */}
        <button
          onClick={onToggleFullscreen}
          className="p-1.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>
    </header>
  );
};
