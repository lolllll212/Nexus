import React from 'react';
import { 
  Mic, 
  Eye, 
  Code2, 
  Layers, 
  Sparkles, 
  Activity, 
  Film, 
  Share2, 
  Cpu, 
  ChevronUp,
  Radio,
  Clock
} from 'lucide-react';
import { AgentStatus, OperatingMode } from '../types';

interface MobileCompactCockpitProps {
  agentStatus: AgentStatus;
  currentMode: OperatingMode;
  onModeChange: (mode: OperatingMode) => void;
  onToggleVoice: () => void;
  onOpenMultimodalBridge: () => void;
  onOpenCodeCompiler: () => void;
  onOpenCanvasBuilder: () => void;
}

const MOBILE_MODE_ORDER: OperatingMode[] = [
  'WORKSPACE',
  'CLAUDE_CHAT',
  'HUD',
  'DASHBOARD',
  'GRAPH',
  'RESEARCH',
  'WORKFLOW',
  'ARCHITECTURE',
  'VIDEO',
];

export const MobileCompactCockpit: React.FC<MobileCompactCockpitProps> = ({
  agentStatus,
  currentMode,
  onModeChange,
  onToggleVoice,
  onOpenMultimodalBridge,
  onOpenCodeCompiler,
  onOpenCanvasBuilder,
}) => {
  const nextMode = () => {
    const index = MOBILE_MODE_ORDER.indexOf(currentMode);
    onModeChange(MOBILE_MODE_ORDER[(index + 1) % MOBILE_MODE_ORDER.length]);
  };

  return (
    <div className="md:hidden fixed inset-x-0 bottom-0 z-40 bg-[#0a0f1d]/95 backdrop-blur-2xl border-t border-[#00f0ff]/30 p-3 pb-[max(1.25rem,env(safe-area-inset-bottom))] flex flex-col gap-2.5 font-mono select-none shadow-[0_-10px_30px_rgba(0,0,0,0.8)]">
      {/* ── Scannable Status Header for Mobile ─────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 text-[10px] px-1 text-slate-400">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className={`h-2 w-2 shrink-0 rounded-full ${agentStatus === 'listening' ? 'bg-[#00ff88] animate-pulse' : agentStatus === 'thinking' ? 'bg-[#ffaa00] animate-pulse' : agentStatus === 'speaking' ? 'bg-amber-400 animate-pulse' : 'bg-cyan-400'}`} />
          <span className="font-bold text-white uppercase tracking-wider">NEXUS MOBILE</span>
          <span className="truncate text-[9px] text-cyan-400">[{agentStatus.toUpperCase()}]</span>
        </div>
        <div className="flex shrink-0 items-center gap-2" title="Current operating mode and voice locale">
          <span className="max-w-[92px] truncate text-emerald-300 font-bold">{currentMode.replace('_', ' ')}</span>
          <span className="text-slate-500">|</span>
          <span className="text-slate-300">EN-IN</span>
        </div>
      </div>

      {/* ── High-Velocity Thumb Interaction Bar (48px targets) ─────────────── */}
      <div className="grid grid-cols-5 gap-1.5">
        {/* Voice Trigger */}
        <button
          type="button"
          onClick={onToggleVoice}
          aria-pressed={agentStatus === 'listening'}
          aria-label={agentStatus === 'listening' ? 'Stop voice input' : 'Start voice input in Indian English'}
          className={`h-12 rounded-2xl flex flex-col items-center justify-center gap-1 font-bold text-[9px] tracking-wider transition-all active:scale-95 cursor-pointer border ${
            agentStatus === 'listening'
              ? 'bg-[#00ff88] text-black border-[#00ff88] shadow-[0_0_15px_#00ff88]'
              : agentStatus === 'thinking'
              ? 'bg-amber-500 text-black border-amber-400 shadow-[0_0_15px_#f59e0b]'
              : 'bg-cyan-950/80 text-cyan-300 border-cyan-400/50 hover:bg-cyan-900'
          }`}
        >
          <Mic className="w-4 h-4" />
          <span>VOICE</span>
        </button>

        {/* Vision / Multimodal Bridge */}
        <button
          onClick={onOpenMultimodalBridge}
          className="h-12 rounded-2xl bg-[#040814] border border-[#00f0ff]/30 text-cyan-300 active:scale-95 flex flex-col items-center justify-center gap-1 font-bold text-[9px] cursor-pointer"
        >
          <Eye className="w-4 h-4 text-cyan-400" />
          <span>VISION</span>
        </button>

        {/* Code Sandbox */}
        <button
          onClick={onOpenCodeCompiler}
          className="h-12 rounded-2xl bg-[#040814] border border-emerald-500/30 text-emerald-300 active:scale-95 flex flex-col items-center justify-center gap-1 font-bold text-[9px] cursor-pointer"
        >
          <Code2 className="w-4 h-4 text-emerald-400" />
          <span>CODE</span>
        </button>

        {/* Canvas Builder */}
        <button
          onClick={onOpenCanvasBuilder}
          className="h-12 rounded-2xl bg-[#040814] border border-purple-500/30 text-purple-300 active:scale-95 flex flex-col items-center justify-center gap-1 font-bold text-[9px] cursor-pointer"
        >
          <Layers className="w-4 h-4 text-purple-400" />
          <span>CANVAS</span>
        </button>

        {/* Layout Mode Switcher */}
        <button
          type="button"
          onClick={nextMode}
          aria-label={`Current mode ${currentMode}. Switch to the next mode`}
          className="h-12 rounded-2xl bg-[#040814] border border-amber-500/30 text-amber-300 active:scale-95 flex flex-col items-center justify-center gap-1 font-bold text-[9px] cursor-pointer"
        >
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="max-w-full truncate px-1">{currentMode.replace('_', ' ')}</span>
        </button>
      </div>
    </div>
  );
};
