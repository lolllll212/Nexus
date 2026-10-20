import React from 'react';
import { Sparkles } from 'lucide-react';

interface JarvisHUDProps {
  ringActive: boolean;
  statusText?: string;
  hasNimKey?: boolean;
  /** Mic armed - pulsing red ring while speech is being captured. */
  listening?: boolean;
  /** Assistant is vocalizing a reply - teal ring. */
  speaking?: boolean;
  onClick?: () => void;
}

export const JarvisHUD: React.FC<JarvisHUDProps> = ({
  ringActive = true,
  statusText = 'ONLINE',
  hasNimKey = false,
  listening = false,
  speaking = false,
  onClick,
}) => {
  const subtitle = listening ? 'LISTENING' : speaking ? 'SPEAKING' : hasNimKey ? 'NIM ACTIVE' : statusText;
  const accent = listening ? '#f87171' : speaking ? '#2dd4bf' : '#00f0ff';
  const accentSoft = listening
    ? 'rgba(248, 113, 113, 0.35)'
    : speaking
    ? 'rgba(45, 212, 191, 0.35)'
    : 'rgba(0, 240, 255, 0.2)';

  // Generate 36 tick marks around the circle
  const ticks = Array.from({ length: 36 }, (_, i) => {
    const angle = i * 10;
    const isMajor = i % 9 === 0;
    const isMedium = i % 3 === 0;
    return { angle, isMajor, isMedium };
  });

  return (
    <div
      onClick={onClick}
      className="relative w-44 h-44 cursor-pointer select-none group flex items-center justify-center transition-transform hover:scale-105"
      title="Click to interact with NEXUS AI (NVIDIA NIM Cortex)"
    >
      {/* Background glow */}
      <div
        className={`absolute inset-0 rounded-full blur-xl transition-all pointer-events-none ${
          listening || speaking ? 'opacity-100 animate-pulse' : 'group-hover:opacity-100 opacity-70'
        }`}
        style={{ backgroundColor: listening ? 'rgba(248,113,113,0.18)' : speaking ? 'rgba(45,212,191,0.18)' : 'rgba(0,240,255,0.10)' }}
      ></div>

      {/* SVG Tick marks & outer ring */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 200 200">
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer static thin boundary */}
        <circle
          cx="100"
          cy="100"
          r="95"
          fill="none"
          stroke={accentSoft}
          strokeWidth="1"
        />

        {/* Tick marks */}
        <g transform="translate(100, 100)">
          {ticks.map(({ angle, isMajor, isMedium }) => {
            const length = isMajor ? 10 : isMedium ? 6 : 3;
            const strokeColor = isMajor
              ? accent
              : isMedium
              ? accentSoft
              : 'rgba(148, 163, 184, 0.25)';
            const strokeW = isMajor ? 2 : 1;
            return (
              <line
                key={angle}
                x1="0"
                y1={-92}
                x2="0"
                y2={-92 + length}
                stroke={strokeColor}
                strokeWidth={strokeW}
                transform={`rotate(${angle})`}
              />
            );
          })}
        </g>
      </svg>

      {/* Ring 1: Outer Rotating Segmented Accent Ring */}
      <div
        className={`absolute inset-2 rounded-full border border-cyan-400/30 ${
          ringActive ? 'animate-spin-slow' : ''
        }`}
        style={{
          borderTopColor: accent,
          borderRightColor: accentSoft,
          borderBottomColor: listening ? '#fca5a5' : speaking ? '#5eead4' : '#00e5bc',
          borderLeftColor: 'transparent',
          boxShadow: `0 0 16px ${accentSoft}, inset 0 0 16px ${accentSoft}`,
        }}
      />

      {/* Ring 2: Counter-Rotating Dashed Ring */}
      <div
        className={`absolute inset-5 rounded-full border border-dashed border-cyan-300/40 ${
          ringActive ? 'animate-spin-reverse' : ''
        }`}
      />

      {/* Ring 3: Inner Thin Fast Rotating Arc */}
      <div
        className={`absolute inset-8 rounded-full border border-cyan-400/20 ${
          ringActive ? 'animate-spin-slow' : ''
        }`}
        style={{
          borderTopColor: '#facc15',
          borderBottomColor: '#00f0ff',
          borderLeftColor: 'transparent',
          borderRightColor: 'transparent',
        }}
      />

      {/* Central Arc Reactor Core */}
      <div className="absolute inset-11 rounded-full bg-gradient-to-tr from-[#04101e] via-[#051c2e] to-[#04101e] border border-cyan-400/50 shadow-[0_0_24px_rgba(0,240,255,0.3),inset_0_0_15px_rgba(0,240,255,0.25)] flex flex-col items-center justify-center text-center p-2 z-10 group-hover:border-cyan-300 transition-colors">
        {/* Sparkle icon / pulse */}
        <div className="relative mb-0.5">
          <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff] animate-ping absolute inset-0"></div>
          <div className="w-2 h-2 rounded-full bg-cyan-300 shadow-[0_0_6px_#00f0ff]"></div>
        </div>

        {/* NEXUS AI Title */}
        <div className="font-mono font-bold text-xs tracking-[0.25em] text-cyan-200 group-hover:text-white transition-colors text-shadow-cyan">
          NEXUS AI
        </div>

        {/* Subtitle status */}
        <div
          className="text-[8.5px] font-mono tracking-widest uppercase mt-0.5 font-semibold"
          style={{ color: accentSoft }}
        >
          {subtitle}
        </div>

        {/* Small audio level dots */}
        <div className="flex gap-0.5 mt-1">
          <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse"></span>
          <span className="w-1 h-1 rounded-full bg-cyan-300 animate-pulse delay-75"></span>
          <span className="w-1 h-1 rounded-full bg-cyan-500 animate-pulse delay-150"></span>
        </div>
      </div>
    </div>
  );
};

export const NexusHUD = JarvisHUD;
