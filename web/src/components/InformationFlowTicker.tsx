import React, { useState, useEffect } from 'react';
import { 
  INITIAL_COGNITIVE_EVENTS 
} from '../data/nexusGraphData';
import { 
  Activity, 
  Brain, 
  Moon, 
  Zap, 
  ChevronUp, 
  ChevronDown, 
  ShieldCheck, 
  Compass, 
  Sparkles,
  Maximize2
} from 'lucide-react';

interface InformationFlowTickerProps {
  onOpenCognitiveModal?: () => void;
}

export const InformationFlowTicker: React.FC<InformationFlowTickerProps> = ({
  onOpenCognitiveModal,
}) => {
  const [events, setEvents] = useState(INITIAL_COGNITIVE_EVENTS);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  // Auto-rotate ticker every 3.5 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % events.length);
    }, 3800);
    return () => clearInterval(timer);
  }, [events.length]);

  const currentEvent = events[currentIndex] || events[0];

  return (
    <div className="select-none font-mono text-xs">
      {/* ── Compact Top/Bottom Floating Ticker ────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-1 rounded-xl bg-slate-950/90 border border-cyan-500/25 backdrop-blur-xl shadow-[0_4px_20px_rgba(0,0,0,0.6)] text-[11px]">
        {/* Layer Badge */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="relative flex h-2 w-2">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
              currentEvent.layer === 'CORTEX' ? 'bg-cyan-400' : 'bg-purple-400'
            }`} />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${
              currentEvent.layer === 'CORTEX' ? 'bg-cyan-500' : 'bg-purple-500'
            }`} />
          </span>
          <span className={`text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded border ${
            currentEvent.layer === 'CORTEX'
              ? 'text-cyan-400 bg-cyan-950/70 border-cyan-500/30'
              : 'text-purple-400 bg-purple-950/70 border-purple-500/30'
          }`}>
            {currentEvent.layer}
          </span>
        </div>

        {/* System & Message */}
        <div className="flex items-center gap-2 overflow-hidden text-slate-300">
          <span className="text-slate-500 font-bold shrink-0">
            [{currentEvent.system}]
          </span>
          <span className="truncate text-slate-200">
            {currentEvent.message}
          </span>
        </div>

        {/* Timestamp & Expand Button */}
        <div className="flex items-center gap-2 shrink-0 ml-auto">
          <span className="text-[9px] text-slate-500 hidden sm:inline">
            {currentEvent.timestamp}
          </span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
            title={isExpanded ? "Collapse Cognitive Stream" : "Expand Cognitive Architecture Stream"}
          >
            {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* ── Expanded Cognitive Architecture Drawer ───────────────────────────── */}
      {isExpanded && (
        <div className="mt-2 p-3.5 rounded-2xl bg-slate-950/95 border border-cyan-500/30 backdrop-blur-2xl shadow-[0_12px_40px_rgba(0,0,0,0.8)] max-h-72 overflow-y-auto space-y-2">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-[10px]">
            <div className="flex items-center gap-2">
              <Brain className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-bold text-white tracking-wider">
                CORTEX (CONSCIOUS ReAct) &bull; SUBCORTEX (DREAMING & SYNTHESIS)
              </span>
            </div>
            <span className="text-slate-500">6 Real-Time Neural Streams Active</span>
          </div>

          <div className="space-y-1.5">
            {events.map((ev) => (
              <div
                key={ev.id}
                className={`p-2 rounded-xl border text-[10px] flex items-start justify-between gap-3 ${
                  ev.layer === 'CORTEX'
                    ? 'bg-cyan-950/20 border-cyan-500/20 text-slate-200'
                    : 'bg-purple-950/20 border-purple-500/20 text-slate-200'
                }`}
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.2 rounded text-[8px] font-bold ${
                      ev.layer === 'CORTEX'
                        ? 'bg-cyan-500/20 text-cyan-300'
                        : 'bg-purple-500/20 text-purple-300'
                    }`}>
                      {ev.layer} :: {ev.system}
                    </span>
                    <span className="text-[9px] text-slate-500">{ev.timestamp}</span>
                  </div>
                  <p className="text-slate-300 text-[10px]">{ev.message}</p>
                </div>
                <span className="px-1.5 py-0.5 rounded text-[8px] font-bold bg-slate-900 border border-slate-700 text-emerald-400 uppercase shrink-0">
                  {ev.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
