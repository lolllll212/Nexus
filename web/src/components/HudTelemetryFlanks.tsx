import React, { useEffect, useState, useMemo } from 'react';
import { 
  Activity, 
  Cpu, 
  Clock, 
  Globe, 
  Wifi, 
  HardDrive, 
  Server, 
  ShieldCheck, 
  Radio, 
  Zap, 
  ChevronLeft, 
  ChevronRight,
  Eye,
  Layers
} from 'lucide-react';

interface HudTelemetryFlanksProps {
  onOpenMultimodalBridge?: () => void;
  onOpenAgentsModal?: () => void;
  onOpenIntegrationsModal?: () => void;
}

export const HudTelemetryFlanks: React.FC<HudTelemetryFlanksProps> = ({
  onOpenMultimodalBridge,
  onOpenAgentsModal,
  onOpenIntegrationsModal,
}) => {
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  // Live simulated real-time telemetry ticks
  const [now, setNow] = useState(new Date());
  const [cpuLoads, setCpuLoads] = useState([38, 52, 29, 64, 45, 31, 58, 42]);
  const [networkIn, setNetworkIn] = useState(1420);
  const [networkOut, setNetworkOut] = useState(860);
  const [latency, setLatency] = useState(14);

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
      setCpuLoads(prev => prev.map(val => Math.min(96, Math.max(18, val + Math.floor(Math.random() * 11 - 5)))));
      setNetworkIn(prev => Math.min(2800, Math.max(600, prev + Math.floor(Math.random() * 240 - 120))));
      setNetworkOut(prev => Math.min(1900, Math.max(400, prev + Math.floor(Math.random() * 180 - 90))));
      setLatency(prev => Math.min(24, Math.max(11, prev + Math.floor(Math.random() * 5 - 2))));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Format World Clocks
  const clocks = useMemo(() => {
    const formatTime = (timeZone: string) => {
      try {
        return new Intl.DateTimeFormat('en-US', {
          timeZone,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }).format(now);
      } catch {
        return now.toTimeString().split(' ')[0];
      }
    };

    return [
      { code: 'PAT', city: 'Patna (IST)', tz: 'Asia/Kolkata', offset: '+05:30', time: formatTime('Asia/Kolkata'), active: true },
      { code: 'UTC', city: 'Universal (Z)', tz: 'UTC', offset: '+00:00', time: formatTime('UTC'), active: true },
      { code: 'SFO', city: 'San Fran (PST)', tz: 'America/Los_Angeles', offset: '-08:00', time: formatTime('America/Los_Angeles'), active: false },
      { code: 'LON', city: 'London (GMT)', tz: 'Europe/London', offset: '+00:00', time: formatTime('Europe/London'), active: false },
      { code: 'TYO', city: 'Tokyo (JST)', tz: 'Asia/Tokyo', offset: '+09:00', time: formatTime('Asia/Tokyo'), active: false },
    ];
  }, [now]);

  return (
    <>
      {/* ── LEFT TELEMETRY FLANK (System CPU & World Time Zones) ─────────────── */}
      <div 
        className={`fixed left-3 top-16 bottom-20 z-30 transition-all duration-300 flex pointer-events-none select-none ${
          leftOpen ? 'w-64 md:w-72' : 'w-9'
        }`}
      >
        <div className="relative w-full h-full pointer-events-auto flex flex-col justify-between glass-obsidian rounded-2xl p-3 border border-[#00f0ff]/25 shadow-[0_0_25px_rgba(0,240,255,0.08)] overflow-hidden">
          {/* Subtle Cyber scanline overlay */}
          <div className="absolute inset-0 scanline pointer-events-none opacity-40" />

          {/* Header & Toggle Button */}
          <div className="flex items-center justify-between pb-2 border-b border-[#00f0ff]/20">
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-[10px] font-mono font-bold tracking-widest text-cyan-200 uppercase">
                SYSTEM TELEMETRY
              </span>
            </div>
            <button
              onClick={() => setLeftOpen(!leftOpen)}
              className="p-1 rounded-md text-cyan-400 hover:text-white hover:bg-cyan-500/20 transition-colors"
              title={leftOpen ? "Collapse Telemetry" : "Expand Telemetry"}
            >
              {leftOpen ? <ChevronLeft className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          </div>

          {leftOpen && (
            <div className="flex-1 overflow-y-auto space-y-3.5 py-2.5 pr-1 text-[10px] font-mono">
              {/* 1. Multi-Core CPU Load Matrix */}
              <div>
                <div className="flex items-center justify-between text-[9px] text-slate-400 uppercase tracking-widest mb-1.5">
                  <span className="flex items-center gap-1">
                    <Activity className="w-3 h-3 text-[#00ff88]" />
                    <span>OCTA-CORE COMPUTE</span>
                  </span>
                  <span className="text-[#00ff88] font-bold">
                    {Math.round(cpuLoads.reduce((a, b) => a + b, 0) / cpuLoads.length)}% AVG
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-1.5">
                  {cpuLoads.map((load, i) => (
                    <div key={i} className="p-1.5 rounded-lg bg-[#040814]/80 border border-[#00f0ff]/15 flex flex-col items-center">
                      <span className="text-[7.5px] text-slate-500 mb-1">C0{i}</span>
                      <div className="w-full h-8 bg-slate-900 rounded-xs flex flex-col justify-end overflow-hidden">
                        <div 
                          className="w-full transition-all duration-500 rounded-xs"
                          style={{
                            height: `${load}%`,
                            backgroundColor: load > 80 ? '#f43f5e' : load > 60 ? '#f59e0b' : '#00f0ff',
                            boxShadow: `0 0 6px ${load > 80 ? '#f43f5e' : load > 60 ? '#f59e0b' : '#00f0ff'}`,
                          }}
                        />
                      </div>
                      <span className="text-[8px] text-cyan-300 font-bold mt-1">{load}%</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 2. Memory & VRAM Allocation */}
              <div className="p-2 rounded-xl bg-[#040814]/70 border border-[#00f0ff]/15 space-y-2">
                <div>
                  <div className="flex justify-between text-[8.5px] text-slate-400 mb-1">
                    <span>RAM ALLOCATION</span>
                    <span className="text-cyan-300">5.4 / 16.0 GB</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-cyan-500 to-[#00ff88] w-[34%] shadow-[0_0_8px_#00f0ff]" />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[8.5px] text-slate-400 mb-1">
                    <span>GPU VRAM TENSOR</span>
                    <span className="text-emerald-400">11.2 / 24.0 GB</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 w-[46%] shadow-[0_0_8px_#00ff88]" />
                  </div>
                </div>
              </div>

              {/* 3. Global World Time Zone Graphs (HUD style) */}
              <div>
                <div className="flex items-center justify-between text-[9px] text-slate-400 uppercase tracking-widest mb-1.5">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-cyan-400" />
                    <span>TIME ZONE MATRIX</span>
                  </span>
                  <span className="text-[8px] text-cyan-500">SYNC: GPS/NTP</span>
                </div>
                <div className="space-y-1">
                  {clocks.map((c) => (
                    <div 
                      key={c.code}
                      className={`px-2 py-1.5 rounded-lg border flex items-center justify-between transition-colors ${
                        c.code === 'PAT'
                          ? 'bg-cyan-950/60 border-cyan-400/50 shadow-[0_0_10px_rgba(0,240,255,0.2)]'
                          : 'bg-[#040814]/60 border-[#00f0ff]/10 text-slate-400'
                      }`}
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${c.code === 'PAT' ? 'bg-[#00ff88] animate-pulse' : 'bg-cyan-400/60'}`} />
                        <div>
                          <span className={`font-bold ${c.code === 'PAT' ? 'text-white' : 'text-slate-300'}`}>
                            {c.code}
                          </span>
                          <span className="text-[8px] text-slate-500 ml-1.5">{c.city}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className={`font-mono font-bold ${c.code === 'PAT' ? 'text-[#00ff88]' : 'text-cyan-300'}`}>
                          {c.time}
                        </span>
                        <span className="text-[7.5px] text-slate-500 block leading-none">{c.offset}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 4. Active Autonomous Neural Agents */}
              <div 
                onClick={onOpenAgentsModal}
                className="p-2 rounded-xl bg-[#040814]/80 border border-cyan-500/20 hover:border-cyan-400/50 transition-colors cursor-pointer group"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[8.5px] text-slate-400 uppercase tracking-wider flex items-center gap-1">
                    <Radio className="w-3 h-3 text-cyan-400" />
                    <span>NEURAL AGENT SWARM</span>
                  </span>
                  <span className="text-[8px] text-emerald-400 font-bold group-hover:underline">10 ACTIVE</span>
                </div>
                <div className="flex gap-1 mt-1">
                  {Array.from({ length: 10 }).map((_, i) => (
                    <div 
                      key={i} 
                      className="flex-1 h-1.5 rounded-full bg-cyan-400/80 animate-pulse" 
                      style={{ animationDelay: `${i * 120}ms` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT TELEMETRY FLANK (Network, Port Stream & Multimodal Engine) ─ */}
      <div 
        className={`fixed right-3 top-16 bottom-20 z-30 transition-all duration-300 flex pointer-events-none select-none ${
          rightOpen ? 'w-64 md:w-72' : 'w-9'
        }`}
      >
        <div className="relative w-full h-full pointer-events-auto flex flex-col justify-between glass-obsidian rounded-2xl p-3 border border-[#00f0ff]/25 shadow-[0_0_25px_rgba(0,240,255,0.08)] overflow-hidden">
          {/* Subtle Cyber scanline overlay */}
          <div className="absolute inset-0 scanline pointer-events-none opacity-40" />

          {/* Header & Toggle Button */}
          <div className="flex items-center justify-between pb-2 border-b border-[#00f0ff]/20">
            <div className="flex items-center gap-2">
              <Wifi className="w-3.5 h-3.5 text-[#00ff88]" />
              <span className="text-[10px] font-mono font-bold tracking-widest text-cyan-200 uppercase">
                I/O & SERVICES
              </span>
            </div>
            <button
              onClick={() => setRightOpen(!rightOpen)}
              className="p-1 rounded-md text-cyan-400 hover:text-white hover:bg-cyan-500/20 transition-colors"
              title={rightOpen ? "Collapse Telemetry" : "Expand Telemetry"}
            >
              {rightOpen ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
            </button>
          </div>

          {rightOpen && (
            <div className="flex-1 overflow-y-auto space-y-3.5 py-2.5 pr-1 text-[10px] font-mono">
              {/* 1. Network Throughput & Latency */}
              <div className="p-2.5 rounded-xl bg-[#040814]/70 border border-[#00f0ff]/15 space-y-2">
                <div className="flex items-center justify-between text-[9px] text-slate-400 uppercase tracking-widest">
                  <span>LOCAL THROUGHPUT</span>
                  <span className="text-emerald-400 font-bold">{latency}ms PING</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-1.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-[7.5px] text-slate-500 block">INBOUND</span>
                    <span className="text-[11px] font-bold text-cyan-300">{networkIn} KB/s</span>
                  </div>
                  <div className="p-1.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-[7.5px] text-slate-500 block">OUTBOUND</span>
                    <span className="text-[11px] font-bold text-[#00ff88]">{networkOut} KB/s</span>
                  </div>
                </div>

                {/* Simulated Sparkline */}
                <div className="h-6 w-full flex items-end gap-0.5 pt-1">
                  {[24, 38, 55, 42, 68, 74, 50, 62, 85, 70, 92, 80, 65, 88].map((val, idx) => (
                    <div 
                      key={idx}
                      className="flex-1 rounded-xs bg-cyan-400/40 hover:bg-cyan-400 transition-colors"
                      style={{ height: `${val}%` }}
                    />
                  ))}
                </div>
              </div>

              {/* 2. Server Port Bindings */}
              <div>
                <div className="flex items-center justify-between text-[9px] text-slate-400 uppercase tracking-widest mb-1.5">
                  <span className="flex items-center gap-1">
                    <Server className="w-3 h-3 text-cyan-400" />
                    <span>BOUND PORTS (0.0.0.0)</span>
                  </span>
                  <span className="text-emerald-400 text-[8px]">ONLINE</span>
                </div>
                <div className="space-y-1">
                  <div className="px-2 py-1.5 rounded-lg bg-[#040814]/60 border border-cyan-500/20 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="font-bold text-slate-200">:8000</span>
                      <span className="text-[8px] text-slate-500">API FASTAPI</span>
                    </div>
                    <span className="text-[8px] text-cyan-300 font-semibold">HEALTHY</span>
                  </div>

                  <div className="px-2 py-1.5 rounded-lg bg-[#040814]/60 border border-cyan-500/20 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="font-bold text-slate-200">:3000</span>
                      <span className="text-[8px] text-slate-500">VITE WEB DEV</span>
                    </div>
                    <span className="text-[8px] text-cyan-300 font-semibold">ACTIVE</span>
                  </div>

                  <div className="px-2 py-1.5 rounded-lg bg-[#040814]/60 border border-cyan-500/20 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="font-bold text-slate-200">:4890</span>
                      <span className="text-[8px] text-slate-500">HOLO DECK</span>
                    </div>
                    <span className="text-[8px] text-cyan-300 font-semibold">LISTENING</span>
                  </div>
                </div>
              </div>

              {/* 3. Multimodal Perception Skill Card Trigger */}
              <div 
                onClick={onOpenMultimodalBridge}
                className="p-2.5 rounded-xl bg-gradient-to-br from-cyan-950/70 to-slate-950/90 border border-cyan-400/40 hover:border-cyan-400 shadow-[0_0_15px_rgba(0,240,255,0.15)] transition-all cursor-pointer group"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 text-cyan-300 font-bold text-[9px] uppercase tracking-wider">
                    <Eye className="w-3.5 h-3.5 text-cyan-400 group-hover:scale-110 transition-transform" />
                    <span>MULTIMODAL BRIDGE</span>
                  </div>
                  <span className="text-[8px] px-1.5 py-0.2 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-400/30">
                    NON-VISION LLM
                  </span>
                </div>
                <p className="text-[8.5px] text-slate-400 leading-tight">
                  Transcodes images & videos into spatial grids, OCR tokens & keyframe logs for text-only models.
                </p>
                <div className="mt-2 flex items-center justify-between text-[8px] text-cyan-400 font-bold group-hover:text-white">
                  <span>LAUNCH MEDIA TRANSCODER</span>
                  <span>→</span>
                </div>
              </div>

              {/* 4. Subcortex Cache & Synapses */}
              <div className="p-2 rounded-xl bg-[#040814]/70 border border-[#00f0ff]/15 flex items-center justify-between">
                <div>
                  <span className="text-[8px] text-slate-500 block uppercase">GRAPH SYNAPSES</span>
                  <span className="text-xs font-bold text-white">1,420 NODES</span>
                </div>
                <div className="text-right">
                  <span className="text-[8px] text-slate-500 block uppercase">CACHE HIT</span>
                  <span className="text-xs font-bold text-[#00ff88]">99.4%</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};
