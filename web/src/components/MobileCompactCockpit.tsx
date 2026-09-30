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

export const MobileCompactCockpit: React.FC<MobileCompactCockpitProps> = ({
  agentStatus,
  currentMode,
  onModeChange,
  onToggleVoice,
  onOpenMultimodalBridge,
  onOpenCodeCompiler,
  onOpenCanvasBuilder,
}) => {
  return (
    <div className="md:hidden fixed inset-x-0 bottom-0 z-40 bg-[#0a0f1d]/95 backdrop-blur-2xl border-t border-[#00f0ff]/30 p-3 pb-6 flex flex-col gap-2.5 font-mono select-none shadow-[0_-10px_30px_rgba(0,0,0,0.8)]">
      {/* ── Scannable Status Header for Mobile ─────────────────────────────── */}
      <div className="flex items-center justify-between text-[10px] px-1 text-slate-400">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${agentStatus === 'listening' ? 'bg-[#00ff88] animate-pulse' : agentStatus === 'thinking' ? 'bg-[#ffaa00] animate-spin' : 'bg-cyan-400'}`} />
          <span className="font-bold text-white uppercase tracking-wider">NEXUS MOBILE</span>
          <span className="text-[9px] text-cyan-400">[{agentStatus.toUpperCase()}]</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400 font-bold">4.8 GHz</span>
          <span className="text-slate-500">|</span>
          <span className="text-slate-300">14ms</span>
        </div>
      </div>

      {/* ── High-Velocity Thumb Interaction Bar (48px targets) ─────────────── */}
      <div className="grid grid-cols-5 gap-1.5">
        {/* Voice Trigger */}
        <button
          onClick={onToggleVoice}
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
          onClick={() => onModeChange(currentMode === 'HUD' ? 'DASHBOARD' : currentMode === 'DASHBOARD' ? 'GRAPH' : 'HUD')}
          className="h-12 rounded-2xl bg-[#040814] border border-amber-500/30 text-amber-300 active:scale-95 flex flex-col items-center justify-center gap-1 font-bold text-[9px] cursor-pointer"
        >
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="truncate">{currentMode}</span>
        </button>
      </div>
    </div>
  );
};
