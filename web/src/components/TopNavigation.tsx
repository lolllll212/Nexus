import React from 'react';
import { 
  Crosshair, 
  Play, 
  Pause, 
  Maximize2, 
  Minimize2, 
  Sparkles, 
  Tag, 
  Radio, 
  Box,
  Globe,
  Zap,
  Layers,
  Eye,
  Camera,
  Code
} from 'lucide-react';

interface TopNavigationProps {
  onFit: () => void;
  isSimulating: boolean;
  onToggleSimulation: () => void;
  showLabels: boolean;
  onToggleLabels: () => void;
  showPulses: boolean;
  onTogglePulses: () => void;
  is3DMode: boolean;
  onToggle3D: () => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onOpenJarvis?: () => void;
  onOpenNexus?: () => void;
  onOpenResearch: () => void;
  onOpenWorkflows: () => void;
  onOpenIntegrations: () => void;
  onOpenVision: () => void;
  onOpenCodingStudio: () => void;
}

export const TopNavigation: React.FC<TopNavigationProps> = ({
  onFit,
  isSimulating,
  onToggleSimulation,
  showLabels,
  onToggleLabels,
  showPulses,
  onTogglePulses,
  is3DMode,
  onToggle3D,
  isFullscreen,
  onToggleFullscreen,
  onOpenJarvis,
  onOpenNexus,
  onOpenResearch,
  onOpenWorkflows,
  onOpenIntegrations,
  onOpenVision,
  onOpenCodingStudio,
}) => {
  const handleOpenNexus = onOpenNexus || onOpenJarvis || (() => {});
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1.5 px-3 py-1.5 rounded-full glass-panel border border-[rgba(0,240,255,0.25)] shadow-[0_8px_32px_rgba(0,0,0,0.6),0_0_15px_rgba(0,240,255,0.1)] select-none max-w-[95vw] overflow-x-auto">
      {/* Fit Button */}
      <button
        onClick={onFit}
        className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-medium text-cyan-200 bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-400/50 hover:border-cyan-300 transition-all shadow-[0_0_10px_rgba(0,240,255,0.2)] shrink-0"
        title="Recenter and fit entire graph into viewport (Back to 2D)"
      >
        <Crosshair className="w-3.5 h-3.5 text-cyan-400" />
        <span>Fit</span>
      </button>

      <div className="w-[1px] h-4 bg-cyan-500/20 mx-0.5 shrink-0"></div>

      {/* Dedicated Claude Coding & Research Studio */}
      <button
        onClick={onOpenCodingStudio}
        className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-amber-200 bg-amber-950/70 hover:bg-amber-900 border border-amber-500/50 hover:border-amber-400 transition-all shadow-[0_0_12px_rgba(245,158,11,0.25)] shrink-0 cursor-pointer"
        title="Open Dedicated Claude-Style Coding Studio (HotKey: C)"
      >
        <Code className="w-3.5 h-3.5 text-amber-400" />
        <span>Claude Studio</span>
      </button>

      {/* Autonomous Research */}
      <button
        onClick={onOpenResearch}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono text-cyan-300 hover:text-white bg-slate-900/60 hover:bg-cyan-950/80 border border-slate-800 hover:border-cyan-400/40 transition-all shrink-0"
        title="Deep Research: Autonomous Multi-Site Web Browser"
      >
        <Globe className="w-3.5 h-3.5 text-cyan-400" />
        <span className="hidden md:inline">Research</span>
      </button>

      {/* Workflows */}
      <button
        onClick={onOpenWorkflows}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono text-cyan-300 hover:text-white bg-slate-900/60 hover:bg-cyan-950/80 border border-slate-800 hover:border-cyan-400/40 transition-all shrink-0"
        title="Workflows: Automated multi-step pipelines"
      >
        <Zap className="w-3.5 h-3.5 text-emerald-400" />
        <span className="hidden md:inline">Workflows</span>
      </button>

      {/* Integrations (GitHub & Gmail) */}
      <button
        onClick={onOpenIntegrations}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono text-cyan-300 hover:text-white bg-slate-900/60 hover:bg-cyan-950/80 border border-slate-800 hover:border-cyan-400/40 transition-all shrink-0"
        title="Integrations: GitHub, Gmail, and Services"
      >
        <Layers className="w-3.5 h-3.5 text-purple-400" />
        <span className="hidden md:inline">Integrations</span>
      </button>

      {/* Vision & Gestures */}
      <button
        onClick={onOpenVision}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono text-cyan-300 hover:text-white bg-slate-900/60 hover:bg-cyan-950/80 border border-slate-800 hover:border-cyan-400/40 transition-all shrink-0"
        title="Vision: Camera HUD, Screen Share & Hand Gestures"
      >
        <Eye className="w-3.5 h-3.5 text-amber-400" />
        <span className="hidden md:inline">Vision & Gestures</span>
      </button>

      <div className="w-[1px] h-4 bg-cyan-500/20 mx-0.5 shrink-0"></div>

      {/* Physics Pause / Play Toggle */}
      <button
        onClick={onToggleSimulation}
        className={`p-1.5 rounded-full transition-colors text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/50 shrink-0 ${
          !isSimulating ? 'text-amber-400 bg-amber-950/40 border border-amber-500/30' : ''
        }`}
        title={isSimulating ? "Freeze simulation physics" : "Resume physics simulation"}
      >
        {isSimulating ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>

      {/* Particle Synapse Pulses Toggle */}
      <button
        onClick={onTogglePulses}
        className={`p-1.5 rounded-full transition-colors shrink-0 ${
          showPulses 
            ? 'text-cyan-400 bg-cyan-950/60 border border-cyan-500/30 shadow-[0_0_8px_rgba(0,240,255,0.3)]' 
            : 'text-slate-500 hover:text-slate-300'
        }`}
        title={showPulses ? "Disable synaptic link pulses" : "Enable animated synaptic link pulses"}
      >
        <Radio className="w-3.5 h-3.5" />
      </button>

      {/* Node Labels Toggle */}
      <button
        onClick={onToggleLabels}
        className={`p-1.5 rounded-full transition-colors shrink-0 ${
          showLabels 
            ? 'text-cyan-400 bg-cyan-950/60 border border-cyan-500/30 shadow-[0_0_8px_rgba(0,240,255,0.3)]' 
            : 'text-slate-500 hover:text-slate-300'
        }`}
        title={showLabels ? "Hide background node labels" : "Always show all node labels"}
      >
        <Tag className="w-3.5 h-3.5" />
      </button>

      {/* 2D / 3D Holo Toggle */}
      <button
        onClick={onToggle3D}
        className={`p-1.5 rounded-full transition-colors shrink-0 ${
          is3DMode 
            ? 'text-amber-300 bg-amber-950/60 border border-amber-400/40 shadow-[0_0_8px_rgba(250,204,21,0.3)]' 
            : 'text-slate-400 hover:text-cyan-300'
        }`}
        title={is3DMode ? "Switch to 2D view" : "Switch to 3D Holo perspective"}
      >
        <Box className="w-3.5 h-3.5" />
      </button>

      <div className="w-[1px] h-4 bg-cyan-500/20 mx-0.5 shrink-0"></div>

      {/* NEXUS AI Assistant Quick Trigger */}
      <button
        onClick={handleOpenNexus}
        className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono text-cyan-200 hover:text-white bg-gradient-to-r from-cyan-950/90 to-blue-950/90 border border-cyan-400/50 hover:border-cyan-300 transition-all shadow-[0_0_10px_rgba(0,240,255,0.25)] shrink-0"
        title="Open NEXUS AI Terminal (NVIDIA NIM)"
      >
        <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-spin-slow" />
        <span>NEXUS AI</span>
      </button>

      {/* Fullscreen Toggle */}
      <button
        onClick={onToggleFullscreen}
        className="p-1.5 rounded-full text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/50 transition-colors shrink-0"
        title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
      >
        {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
};
