import React, { useMemo, useState, useEffect } from 'react';
import { 
  Sparkles, 
  Mic, 
  Zap, 
  Activity, 
  Layers, 
  Code2, 
  Eye, 
  Film, 
  Network,
  ShieldCheck,
  AlertTriangle,
  Radio,
  Cpu
} from 'lucide-react';
import { AgentStatus, TaskDifficulty } from '../types';

interface CyberneticOrbProps {
  agentStatus: AgentStatus;
  taskDifficulty?: TaskDifficulty;
  onToggleVoice: () => void;
  onOpenMultimodalBridge: () => void;
  onOpenCodeCompiler: () => void;
  onOpenCanvasBuilder: () => void;
  onOpenVideoStudio: () => void;
  onOpenGraphMode: () => void;
  isAccelerated?: boolean;
  puffTrigger?: number; // Increment to trigger action ripple "puff"
}

export const CyberneticOrb: React.FC<CyberneticOrbProps> = ({
  agentStatus,
  taskDifficulty = 'low',
  onToggleVoice,
  onOpenMultimodalBridge,
  onOpenCodeCompiler,
  onOpenCanvasBuilder,
  onOpenVideoStudio,
  onOpenGraphMode,
  isAccelerated = false,
  puffTrigger = 0,
}) => {
  // Action Ripple "Puff" animation state
  const [showPuff, setShowPuff] = useState(false);

  useEffect(() => {
    if (puffTrigger > 0) {
      setShowPuff(true);
      const timer = setTimeout(() => setShowPuff(false), 850);
      return () => clearTimeout(timer);
    }
  }, [puffTrigger]);

  // Generate 72 calibration tick marks for Arc Reactor periphery
  const ticks = useMemo(() => {
    return Array.from({ length: 72 }, (_, i) => {
      const angle = i * 5;
      const isMajor = i % 18 === 0;   // 0, 90, 180, 270 deg
      const isMedium = i % 6 === 0;   // Every 30 deg
      return { angle, isMajor, isMedium };
    });
  }, []);

  // 12 Electromagnet Coils
  const coils = useMemo(() => {
    return Array.from({ length: 12 }, (_, i) => ({
      angle: i * 30,
      index: i,
    }));
  }, []);

  // Module 3: Dynamic Respiration Color Matrix by Task Difficulty
  const difficultyColors = useMemo(() => {
    switch (taskDifficulty) {
      case 'critical':
        return {
          glow: 'rgba(244, 63, 94, 0.45)',
          border: 'border-rose-500',
          hex: '#f43f5e',
          text: 'text-rose-400',
          badge: 'bg-rose-950/80 border-rose-500/50 text-rose-300',
        };
      case 'high':
        return {
          glow: 'rgba(255, 170, 0, 0.45)',
          border: 'border-amber-400',
          hex: '#ffaa00',
          text: 'text-amber-400',
          badge: 'bg-amber-950/80 border-amber-500/50 text-amber-300',
        };
      case 'medium':
        return {
          glow: 'rgba(0, 255, 136, 0.4)',
          border: 'border-emerald-400',
          hex: '#00ff88',
          text: 'text-emerald-400',
          badge: 'bg-emerald-950/80 border-emerald-500/50 text-emerald-300',
        };
      case 'low':
      default:
        return {
          glow: 'rgba(0, 240, 255, 0.35)',
          border: 'border-cyan-400',
          hex: '#00f0ff',
          text: 'text-cyan-400',
          badge: 'bg-cyan-950/80 border-cyan-500/50 text-cyan-300',
        };
    }
  }, [taskDifficulty]);

  // State-specific styling
  const statusTheme = useMemo(() => {
    switch (agentStatus) {
      case 'listening':
        return {
          title: 'AUDIO SENSOR ACTIVE',
          subtext: 'LISTENING TO VOCAL STREAM [M]',
          ringColor: '#00ff88',
          accent: '#10b981',
          speedClass1: 'animate-spin-layer-1-fast',
          speedClass2: 'animate-spin-layer-2-fast',
          speedClass3: 'animate-spin-layer-3',
        };
      case 'thinking':
        return {
          title: 'NEURAL SYNAPSE COMPUTE',
          subtext: 'DISPATCHING TO SUBCORTEX AGENTS',
          ringColor: '#ffaa00',
          accent: '#f59e0b',
          speedClass1: 'animate-spin-layer-1-fast',
          speedClass2: 'animate-spin-layer-2-fast',
          speedClass3: 'animate-spin-layer-3-fast',
        };
      case 'speaking':
        return {
          title: 'VOCAL SYNTHESIS ACTIVE',
          subtext: 'TRANSMITTING SPOKEN RESPONSE',
          ringColor: '#00f0ff',
          accent: '#06b6d4',
          speedClass1: 'animate-spin-layer-1',
          speedClass2: 'animate-spin-layer-2',
          speedClass3: 'animate-spin-layer-3',
        };
      case 'idle':
      default:
        return {
          title: 'QUANTUM CORE NOMINAL',
          subtext: 'STANDBY // READY FOR INSTRUCTION',
          ringColor: difficultyColors.hex,
          accent: '#38bdf8',
          speedClass1: isAccelerated ? 'animate-spin-layer-1-fast' : 'animate-spin-layer-1',
          speedClass2: isAccelerated ? 'animate-spin-layer-2-fast' : 'animate-spin-layer-2',
          speedClass3: isAccelerated ? 'animate-spin-layer-3-fast' : 'animate-spin-layer-3',
        };
    }
  }, [agentStatus, difficultyColors, isAccelerated]);

  return (
    <div className="relative flex flex-col items-center justify-center select-none py-2 font-mono">
      {/* ── Background Ambient Radial Respiration Aura (1.5-second loop) ───── */}
      <div 
        className="absolute w-[460px] h-[460px] rounded-full blur-3xl pointer-events-none transition-all duration-700 animate-pulse-respiration"
        style={{ backgroundColor: difficultyColors.glow }}
      />

      {/* ── Action Ripple "Puff" expanding animation (Exact ms trigger) ────── */}
      {showPuff && (
        <div 
          className="absolute w-64 h-64 rounded-full border-2 animate-puff-ripple pointer-events-none z-30"
          style={{ borderColor: statusTheme.ringColor, boxShadow: `0 0 30px ${statusTheme.ringColor}` }}
        />
      )}

      {/* ── Outer Coordinate Calibration Grid & Three Concentric Layers ─────── */}
      <div className="relative w-88 h-88 md:w-[420px] md:h-[420px] flex items-center justify-center">
        
        {/* SVG Perimeter Compass, Ticks & Radar Radial Sweep */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 420 420">
          <defs>
            <filter id="neon-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Static outer thin boundary */}
          <circle
            cx="210"
            cy="210"
            r="202"
            fill="none"
            stroke="rgba(0, 240, 255, 0.18)"
            strokeWidth="1"
            strokeDasharray="4 6"
          />

          {/* Perimeter 72 tick marks */}
          <g transform="translate(210, 210)">
            {ticks.map(({ angle, isMajor, isMedium }) => {
              const length = isMajor ? 14 : isMedium ? 8 : 4;
              const strokeColor = isMajor
                ? statusTheme.ringColor
                : isMedium
                ? 'rgba(0, 240, 255, 0.55)'
                : 'rgba(0, 240, 255, 0.2)';
              const strokeW = isMajor ? 2.5 : 1;
              return (
                <line
                  key={angle}
                  x1="0"
                  y1={-200}
                  x2="0"
                  y2={-200 + length}
                  stroke={strokeColor}
                  strokeWidth={strokeW}
                  transform={`rotate(${angle})`}
                />
              );
            })}

            {/* Cardinal Degree Markers */}
            <text x="0" y="-178" fill="#00f0ff" fontSize="7.5" fontFamily="monospace" textAnchor="middle" opacity="0.7">000° SEC-A</text>
            <text x="178" y="3" fill="#00f0ff" fontSize="7.5" fontFamily="monospace" textAnchor="middle" opacity="0.7">090° AST-OK</text>
            <text x="0" y="184" fill="#00f0ff" fontSize="7.5" fontFamily="monospace" textAnchor="middle" opacity="0.7">180° CORE</text>
            <text x="-178" y="3" fill="#00f0ff" fontSize="7.5" fontFamily="monospace" textAnchor="middle" opacity="0.7">270° SYNC</text>
          </g>
        </svg>

        {/* ── CONCENTRIC LAYER 3: Outer Critical Alerts & Security Layer ─────── */}
        {/* Rotates clockwise at 36s (or 8s accelerated) */}
        <div 
          className={`absolute inset-2 rounded-full border border-cyan-400/20 ${statusTheme.speedClass3} pointer-events-none`}
          style={{
            borderTopColor: taskDifficulty === 'critical' ? '#f43f5e' : 'rgba(0, 240, 255, 0.6)',
            borderRightColor: 'rgba(0, 240, 255, 0.1)',
            borderBottomColor: 'rgba(0, 255, 136, 0.4)',
            borderLeftColor: 'transparent',
          }}
        >
          {/* Layer 3 Peripheral Beacons */}
          <div className="absolute top-1 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-[#0a0f1d] border border-cyan-400/40 text-[7px] text-cyan-300 font-bold tracking-wider">
            [L3: SEC_HARDENED // THREAT: 0]
          </div>
          <div className="absolute bottom-1 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-[#0a0f1d] border border-emerald-400/40 text-[7px] text-emerald-300 font-bold tracking-wider">
            [AST GUARD: ACTIVE]
          </div>
        </div>

        {/* ── CONCENTRIC LAYER 2: Middle Active Tasks Layer ──────────────────── */}
        {/* Counter-rotates at 22s (or 4.5s accelerated) */}
        <div 
          className={`absolute inset-7 rounded-full border-2 border-dashed ${statusTheme.speedClass2} pointer-events-none`}
          style={{
            borderColor: `${statusTheme.accent}44`,
            borderTopColor: statusTheme.ringColor,
            borderBottomColor: statusTheme.ringColor,
          }}
        >
          {/* Layer 2 Active Task Badges */}
          <div className="absolute -top-3 left-1/4 px-1.5 py-0.2 rounded-md bg-[#040914] border border-[#00f0ff]/30 text-[6.5px] text-cyan-200">
            SWARM: 10 ACTIVE
          </div>
          <div className="absolute -bottom-3 right-1/4 px-1.5 py-0.2 rounded-md bg-[#040914] border border-[#00ff88]/30 text-[6.5px] text-[#00ff88]">
            PERCEPTION: OK
          </div>
        </div>

        {/* ── CONCENTRIC LAYER 1: Inner Low-Level Telemetry Stats Layer ──────── */}
        {/* Rotates clockwise at 14s (or 3.5s accelerated) */}
        <div 
          className={`absolute inset-13 rounded-full border border-cyan-400/30 ${statusTheme.speedClass1} pointer-events-none`}
          style={{
            borderTopColor: statusTheme.ringColor,
            borderRightColor: 'transparent',
            borderBottomColor: 'rgba(0, 240, 255, 0.3)',
            borderLeftColor: 'transparent',
            boxShadow: `0 0 20px ${statusTheme.ringColor}22`,
          }}
        >
          {/* Layer 1 Low-Level Stats Badges */}
          <div className="absolute top-0 right-2 px-1.5 py-0.2 rounded-sm bg-[#0a0f1d] border border-cyan-400/50 text-[6.5px] text-cyan-300 font-bold">
            CPU: 42%
          </div>
          <div className="absolute bottom-0 left-2 px-1.5 py-0.2 rounded-sm bg-[#0a0f1d] border border-cyan-400/50 text-[6.5px] text-cyan-300 font-bold">
            RAM: 5.4G
          </div>
        </div>

        {/* 12 Arc Reactor Electromagnetic Coils */}
        <div className="absolute inset-17 rounded-full pointer-events-none">
          {coils.map(({ angle, index }) => (
            <div
              key={index}
              className="absolute inset-0 flex items-start justify-center"
              style={{ transform: `rotate(${angle}deg)` }}
            >
              <div 
                className="w-4 h-3 rounded-xs bg-gradient-to-b from-[#0a1e38] to-[#040d1a] border border-cyan-400/40 shadow-[0_0_8px_rgba(0,240,255,0.3)] flex items-center justify-center"
              >
                <div 
                  className="w-2 h-0.5 rounded-xs"
                  style={{ backgroundColor: statusTheme.ringColor }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Audio Equalizer dancing waves (in Speaking or Listening) */}
        {(agentStatus === 'speaking' || agentStatus === 'listening') && (
          <div 
            className="absolute inset-15 rounded-full border-2 animate-ripple-wave pointer-events-none"
            style={{ borderColor: statusTheme.ringColor }}
          />
        )}

        {/* ── CENTRAL ARC REACTOR CORE (Interactive Centerpiece) ─────────────── */}
        <div
          onClick={onToggleVoice}
          className={`relative w-40 h-40 md:w-44 md:h-44 rounded-full cursor-pointer flex flex-col items-center justify-center p-3 text-center transition-all duration-300 z-10 glass-obsidian border-2 ${difficultyColors.border} animate-pulse-respiration hover:scale-105 active:scale-95 group shadow-[0_0_40px_rgba(0,240,255,0.35),inset_0_0_25px_rgba(0,240,255,0.2)]`}
          title="Click to toggle Voice Listening Mode [M] / Wake NEXUS"
        >
          {/* Inner pulsating plasma orb */}
          <div className="relative mb-1">
            <div 
              className="w-4 h-4 rounded-full animate-ping absolute inset-0 opacity-75"
              style={{ backgroundColor: statusTheme.ringColor }}
            />
            <div 
              className="w-4 h-4 rounded-full shadow-[0_0_12px_#00f0ff] flex items-center justify-center"
              style={{ backgroundColor: statusTheme.ringColor }}
            >
              {agentStatus === 'listening' ? (
                <Mic className="w-2.5 h-2.5 text-black" />
              ) : agentStatus === 'thinking' ? (
                <Zap className="w-2.5 h-2.5 text-black" />
              ) : (
                <Sparkles className="w-2.5 h-2.5 text-black" />
              )}
            </div>
          </div>

          {/* AI Title */}
          <div className="font-mono font-black text-sm tracking-[0.3em] text-white group-hover:text-cyan-200 transition-colors drop-shadow-[0_0_10px_rgba(0,240,255,0.8)]">
            NEXUS
          </div>

          {/* Frequency & Sub-system */}
          <div className="text-[9px] font-mono tracking-widest text-cyan-300/80 font-bold uppercase mt-0.5">
            4.80 GHz // {agentStatus.toUpperCase()}
          </div>

          {/* Live Audio Equalizer Waveform Bars */}
          <div className="flex items-center gap-1 my-1.5 h-3">
            {[4, 8, 12, 16, 10, 6, 14, 8].map((h, i) => (
              <div 
                key={i}
                className="w-0.5 rounded-full bg-cyan-400 transition-all duration-150"
                style={{ 
                  height: agentStatus === 'speaking' || agentStatus === 'listening'
                    ? `${Math.max(3, (h * (Math.random() * 0.8 + 0.6)))}px`
                    : '3px',
                  backgroundColor: statusTheme.ringColor,
                }}
              />
            ))}
          </div>

          {/* State Indicator Badge */}
          <div className={`px-2 py-0.5 rounded-full text-[8.5px] font-mono font-bold tracking-wider uppercase border ${difficultyColors.badge} flex items-center gap-1 shadow-sm`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            <span>{agentStatus === 'idle' ? 'STANDBY' : agentStatus}</span>
          </div>

          {/* Mic hotkey indicator */}
          <span className="text-[7.5px] text-slate-400 font-mono mt-1 opacity-70 group-hover:opacity-100 transition-opacity">
            CLICK OR PRESS [M]
          </span>
        </div>
      </div>

      {/* ── Status Telemetry Ribbon ─────────────────────────────────────────── */}
      <div className="mt-3 flex flex-col items-center gap-0.5 text-center">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span className="text-xs font-mono font-bold tracking-[0.2em] text-slate-200">
            {statusTheme.title}
          </span>
          <span className={`text-[8.5px] px-1.5 py-0.2 rounded font-bold uppercase ${difficultyColors.badge}`}>
            DIFF: {taskDifficulty.toUpperCase()}
          </span>
        </div>
        <div className="text-[10px] font-mono tracking-widest text-cyan-400/80">
          {statusTheme.subtext}
        </div>
      </div>

      {/* ── Contextual HUD Quick-Summon Tools ───────────────────────────────── */}
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2 max-w-2xl px-4 z-20">
        <button
          onClick={onOpenMultimodalBridge}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/85 hover:bg-[#00f0ff]/15 border border-[#00f0ff]/35 hover:border-[#00f0ff]/70 text-cyan-300 hover:text-white text-[10.5px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(0,240,255,0.15)] hover:scale-102 cursor-pointer"
        >
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span>✦ MULTIMODAL BRIDGE</span>
        </button>

        <button
          onClick={onOpenCodeCompiler}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/85 hover:bg-emerald-500/15 border border-emerald-500/35 hover:border-emerald-400 text-emerald-300 hover:text-white text-[10.5px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Code2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>⚡ CODE COMPILER</span>
        </button>

        <button
          onClick={onOpenCanvasBuilder}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/85 hover:bg-purple-500/15 border border-purple-500/35 hover:border-purple-400 text-purple-300 hover:text-white text-[10.5px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Layers className="w-3.5 h-3.5 text-purple-400" />
          <span>◈ CANVAS BUILDER</span>
        </button>

        <button
          onClick={onOpenVideoStudio}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/85 hover:bg-amber-500/15 border border-amber-500/35 hover:border-amber-400 text-amber-300 hover:text-white text-[10.5px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Film className="w-3.5 h-3.5 text-amber-400" />
          <span>🎬 VIDEO STUDIO</span>
        </button>

        <button
          onClick={onOpenGraphMode}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/85 hover:bg-cyan-500/15 border border-cyan-500/35 hover:border-cyan-400 text-slate-300 hover:text-cyan-200 text-[10.5px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Network className="w-3.5 h-3.5 text-cyan-400" />
          <span>🌐 COSMOS GRAPH</span>
        </button>
      </div>
    </div>
  );
};
