import React, { useMemo } from 'react';
import { 
  Sparkles, 
  Mic, 
  MicOff, 
  Zap, 
  Activity, 
  Layers, 
  Code2, 
  Eye, 
  Film, 
  Network,
  Cpu
} from 'lucide-react';
import { AgentStatus } from '../types';

interface CyberneticOrbProps {
  agentStatus: AgentStatus;
  onToggleVoice: () => void;
  onOpenMultimodalBridge: () => void;
  onOpenCodeCompiler: () => void;
  onOpenCanvasBuilder: () => void;
  onOpenVideoStudio: () => void;
  onOpenGraphMode: () => void;
}

export const CyberneticOrb: React.FC<CyberneticOrbProps> = ({
  agentStatus,
  onToggleVoice,
  onOpenMultimodalBridge,
  onOpenCodeCompiler,
  onOpenCanvasBuilder,
  onOpenVideoStudio,
  onOpenGraphMode,
}) => {
  // Generate 72 calibration tick marks for Arc Reactor periphery
  const ticks = useMemo(() => {
    return Array.from({ length: 72 }, (_, i) => {
      const angle = i * 5;
      const isMajor = i % 18 === 0;   // 0, 90, 180, 270 deg
      const isMedium = i % 6 === 0;   // Every 30 deg
      return { angle, isMajor, isMedium };
    });
  }, []);

  // 12 Arc Reactor Electromagnet Coils
  const coils = useMemo(() => {
    return Array.from({ length: 12 }, (_, i) => ({
      angle: i * 30,
      index: i,
    }));
  }, []);

  // State-specific styling
  const statusTheme = useMemo(() => {
    switch (agentStatus) {
      case 'listening':
        return {
          coreGlow: 'bg-[#00ff88]/20 shadow-[0_0_60px_#00ff88]',
          borderColor: 'border-[#00ff88]/80',
          ringColor: '#00ff88',
          accentColor: '#10b981',
          title: 'AUDIO SENSOR ACTIVE',
          subtext: 'LISTENING TO VOCAL STREAM [M]',
          pulseClass: 'animate-pulse-listening',
          badgeBg: 'bg-emerald-950/80 border-emerald-500/50 text-emerald-300',
        };
      case 'thinking':
        return {
          coreGlow: 'bg-[#ffaa00]/25 shadow-[0_0_60px_#ffaa00]',
          borderColor: 'border-[#ffaa00]/80',
          ringColor: '#ffaa00',
          accentColor: '#f59e0b',
          title: 'NEURAL SYNAPSE COMPUTE',
          subtext: 'DISPATCHING TO SUBCORTEX AGENTS',
          pulseClass: 'animate-pulse-thinking',
          badgeBg: 'bg-amber-950/80 border-amber-500/50 text-amber-300',
        };
      case 'speaking':
        return {
          coreGlow: 'bg-[#00f0ff]/30 shadow-[0_0_70px_#00f0ff]',
          borderColor: 'border-[#00f0ff]',
          ringColor: '#00f0ff',
          accentColor: '#06b6d4',
          title: 'VOCAL SYNTHESIS ACTIVE',
          subtext: 'TRANSMITTING SPOKEN RESPONSE',
          pulseClass: 'animate-pulse-core',
          badgeBg: 'bg-cyan-950/80 border-cyan-400/60 text-cyan-200',
        };
      case 'idle':
      default:
        return {
          coreGlow: 'bg-[#00f0ff]/15 shadow-[0_0_45px_rgba(0,240,255,0.4)]',
          borderColor: 'border-cyan-400/50',
          ringColor: '#00f0ff',
          accentColor: '#38bdf8',
          title: 'QUANTUM CORE NOMINAL',
          subtext: 'STANDBY // READY FOR INSTRUCTION',
          pulseClass: 'animate-pulse-core',
          badgeBg: 'bg-slate-950/80 border-cyan-500/30 text-cyan-400',
        };
    }
  }, [agentStatus]);

  return (
    <div className="relative flex flex-col items-center justify-center select-none py-4">
      {/* ── Background Ambient Radial Aura ──────────────────────────────────── */}
      <div 
        className={`absolute w-[440px] h-[440px] rounded-full blur-3xl pointer-events-none transition-all duration-700 ${statusTheme.coreGlow}`} 
      />

      {/* ── Outer Coordinate Calibration Grid (HUD Style) ───────────────────── */}
      <div className="relative w-84 h-84 md:w-96 md:h-96 flex items-center justify-center">
        {/* SVG Arc Reactor Compass & Ticks */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 400 400">
          <defs>
            <filter id="neon-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Static outer thin guide circle */}
          <circle
            cx="200"
            cy="200"
            r="192"
            fill="none"
            stroke="rgba(0, 240, 255, 0.15)"
            strokeWidth="1"
            strokeDasharray="4 4"
          />

          {/* Perimeter 72 tick marks */}
          <g transform="translate(200, 200)">
            {ticks.map(({ angle, isMajor, isMedium }) => {
              const length = isMajor ? 14 : isMedium ? 8 : 4;
              const strokeColor = isMajor
                ? statusTheme.ringColor
                : isMedium
                ? 'rgba(0, 240, 255, 0.5)'
                : 'rgba(0, 240, 255, 0.2)';
              const strokeW = isMajor ? 2.5 : 1;
              return (
                <line
                  key={angle}
                  x1="0"
                  y1={-190}
                  x2="0"
                  y2={-190 + length}
                  stroke={strokeColor}
                  strokeWidth={strokeW}
                  transform={`rotate(${angle})`}
                />
              );
            })}

            {/* Degree Markings */}
            <text x="0" y="-168" fill="#00f0ff" fontSize="7" fontFamily="monospace" textAnchor="middle" opacity="0.6">000° N</text>
            <text x="168" y="3" fill="#00f0ff" fontSize="7" fontFamily="monospace" textAnchor="middle" opacity="0.6">090° E</text>
            <text x="0" y="174" fill="#00f0ff" fontSize="7" fontFamily="monospace" textAnchor="middle" opacity="0.6">180° S</text>
            <text x="-168" y="3" fill="#00f0ff" fontSize="7" fontFamily="monospace" textAnchor="middle" opacity="0.6">270° W</text>
          </g>
        </svg>

        {/* ── Ring 1: Segmented Primary Arc Track (Clockwise) ────────────────── */}
        <div
          className={`absolute inset-4 rounded-full border border-cyan-400/25 ${
            agentStatus === 'thinking' ? 'animate-spin-fast' : 'animate-spin-slow'
          }`}
          style={{
            borderTopColor: statusTheme.ringColor,
            borderRightColor: 'rgba(0, 240, 255, 0.15)',
            borderBottomColor: statusTheme.ringColor,
            borderLeftColor: 'transparent',
            boxShadow: `0 0 25px ${statusTheme.ringColor}33`,
          }}
        />

        {/* ── Ring 2: Counter-Rotating Dashed Chrono Gear (Counter-Clockwise) ── */}
        <div
          className={`absolute inset-8 rounded-full border-2 border-dashed ${
            agentStatus === 'thinking' ? 'animate-spin-reverse' : 'animate-spin-reverse'
          }`}
          style={{
            borderColor: `${statusTheme.accentColor}44`,
          }}
        />

        {/* ── Ring 3: 12 Arc Reactor Electromagnetic Coils ───────────────────── */}
        <div className="absolute inset-12 rounded-full pointer-events-none">
          {coils.map(({ angle, index }) => (
            <div
              key={index}
              className="absolute inset-0 flex items-start justify-center"
              style={{ transform: `rotate(${angle}deg)` }}
            >
              <div 
                className="w-4 h-3.5 rounded-sm bg-gradient-to-b from-[#0a1e38] to-[#040d1a] border border-cyan-400/40 shadow-[0_0_8px_rgba(0,240,255,0.3)] flex items-center justify-center"
              >
                <div 
                  className="w-2 h-1 rounded-xs"
                  style={{ backgroundColor: statusTheme.ringColor }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* ── Audio Harmonic Shockwave Waves (Active in Speaking/Listening) ──── */}
        {(agentStatus === 'speaking' || agentStatus === 'listening') && (
          <div 
            className="absolute inset-10 rounded-full border-2 border-cyan-400/60 animate-ripple-wave pointer-events-none"
            style={{ borderColor: statusTheme.ringColor }}
          />
        )}

        {/* ── Ring 4: Inner Precision Caliper Ring ───────────────────────────── */}
        <div 
          className="absolute inset-16 rounded-full border border-cyan-500/30 flex items-center justify-center pointer-events-none"
        >
          <div className="w-full h-full rounded-full border border-dashed border-cyan-400/20 animate-spin-slow" />
        </div>

        {/* ── CENTRAL ARC REACTOR CORE (Interactive Centerpiece) ─────────────── */}
        <div
          onClick={onToggleVoice}
          className={`relative w-40 h-40 md:w-44 md:h-44 rounded-full cursor-pointer flex flex-col items-center justify-center p-3 text-center transition-all duration-300 z-10 glass-obsidian border-2 ${statusTheme.borderColor} ${statusTheme.pulseClass} hover:scale-105 active:scale-95 group shadow-[0_0_40px_rgba(0,240,255,0.3),inset_0_0_25px_rgba(0,240,255,0.2)]`}
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

          {/* State Indicator Badge */}
          <div className={`mt-2 px-2 py-0.5 rounded-full text-[8.5px] font-mono font-bold tracking-wider uppercase border ${statusTheme.badgeBg} flex items-center gap-1 shadow-sm`}>
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
      <div className="mt-4 flex flex-col items-center gap-1 text-center">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span className="text-xs font-mono font-bold tracking-[0.2em] text-slate-200">
            {statusTheme.title}
          </span>
        </div>
        <div className="text-[10px] font-mono tracking-widest text-cyan-400/80">
          {statusTheme.subtext}
        </div>
      </div>

      {/* ── Contextual HUD Quick-Summon Tools (Minimal Overload) ─────────────── */}
      <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5 max-w-2xl px-4 z-20">
        {/* Multimodal Bridge Skill Tool */}
        <button
          onClick={onOpenMultimodalBridge}
          className="px-3.5 py-1.5 rounded-xl bg-[#0a0f1d]/80 hover:bg-[#00f0ff]/15 border border-[#00f0ff]/30 hover:border-[#00f0ff]/70 text-cyan-300 hover:text-white text-[11px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(0,240,255,0.12)] hover:shadow-[0_0_20px_rgba(0,240,255,0.3)] hover:scale-102 cursor-pointer"
        >
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span>✦ MULTIMODAL BRIDGE (NON-VISION)</span>
        </button>

        {/* Code Compiler */}
        <button
          onClick={onOpenCodeCompiler}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/80 hover:bg-emerald-500/15 border border-emerald-500/30 hover:border-emerald-400 text-emerald-300 hover:text-white text-[11px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Code2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>⚡ CODE COMPILER</span>
        </button>

        {/* Canvas Builder */}
        <button
          onClick={onOpenCanvasBuilder}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/80 hover:bg-purple-500/15 border border-purple-500/30 hover:border-purple-400 text-purple-300 hover:text-white text-[11px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Layers className="w-3.5 h-3.5 text-purple-400" />
          <span>◈ CANVAS BUILDER</span>
        </button>

        {/* Video Studio */}
        <button
          onClick={onOpenVideoStudio}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/80 hover:bg-amber-500/15 border border-amber-500/30 hover:border-amber-400 text-amber-300 hover:text-white text-[11px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Film className="w-3.5 h-3.5 text-amber-400" />
          <span>🎬 VIDEO STUDIO</span>
        </button>

        {/* Knowledge Cosmos Graph */}
        <button
          onClick={onOpenGraphMode}
          className="px-3 py-1.5 rounded-xl bg-[#0a0f1d]/80 hover:bg-cyan-500/15 border border-cyan-500/30 hover:border-cyan-400 text-slate-300 hover:text-cyan-200 text-[11px] font-mono font-bold tracking-wider flex items-center gap-2 transition-all shadow-sm hover:scale-102 cursor-pointer"
        >
          <Network className="w-3.5 h-3.5 text-cyan-400" />
          <span>🌐 COSMOS GRAPH</span>
        </button>
      </div>
    </div>
  );
};
