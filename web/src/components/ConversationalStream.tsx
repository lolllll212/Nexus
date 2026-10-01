import React, { useRef, useEffect } from 'react';
import { 
  Bot, 
  User, 
  Terminal, 
  Sparkles, 
  Cpu, 
  Zap, 
  Copy, 
  Check, 
  Maximize2, 
  Minimize2, 
  X,
  ChevronDown,
  ChevronRight,
  Eye,
  Code2,
  Layers,
  Film
} from 'lucide-react';
import { ConversationalMessage, TaskDifficulty } from '../types';

interface ConversationalStreamProps {
  messages: ConversationalMessage[];
  isOpen: boolean;
  onToggleOpen: () => void;
  onTriggerAction?: (action: string, payload?: any) => void;
  isStreaming?: boolean;
}

export const ConversationalStream: React.FC<ConversationalStreamProps> = ({
  messages,
  isOpen,
  onToggleOpen,
  onTriggerAction,
  isStreaming = false,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  if (!isOpen) {
    return (
      <button
        onClick={onToggleOpen}
        className="fixed bottom-24 right-6 z-30 px-3.5 py-2 rounded-2xl glass-obsidian border border-[#00f0ff]/40 text-cyan-300 hover:text-white hover:border-[#00f0ff]/80 font-mono text-xs font-bold tracking-wider flex items-center gap-2 shadow-[0_0_20px_rgba(0,240,255,0.2)] transition-all cursor-pointer hover:scale-105"
      >
        <Terminal className="w-3.5 h-3.5 text-cyan-400" />
        <span>CHAT WITH NEXUS</span>
        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-24 right-6 z-30 w-96 md:w-[420px] max-h-[460px] flex flex-col glass-obsidian rounded-2xl border border-[#00f0ff]/30 shadow-[0_16px_40px_rgba(0,0,0,0.8),0_0_25px_rgba(0,240,255,0.15)] font-mono select-none overflow-hidden animate-fade-in">
      {/* ── Conversational Stream Header ─────────────────────────────────────── */}
      <div className="p-3 bg-[#060a16]/95 border-b border-[#00f0ff]/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-[10px] font-bold tracking-widest text-cyan-200 uppercase">
                CHAT WITH NEXUS
              </span>
          <span className="px-1.5 py-0.2 rounded bg-cyan-950/80 border border-cyan-400/30 text-[8px] text-cyan-300">
            NEXUS CORTEX
          </span>
        </div>

        <button
          onClick={onToggleOpen}
          className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors cursor-pointer"
        >
          <Minimize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── Message Feed ────────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3.5 space-y-3 text-xs">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';

          return (
            <div 
              key={msg.id} 
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
            >
              {/* Header label & timestamp */}
              <div className="flex items-center gap-1.5 mb-1 text-[8px] text-slate-400">
                {isUser ? (
                  <>
                    <span>{msg.timestamp}</span>
                    <span className="text-cyan-400 font-bold">OPERATOR</span>
                  </>
                ) : (
                  <>
                    <span className="text-cyan-300 font-bold flex items-center gap-1">
                      <Sparkles className="w-2.5 h-2.5 text-cyan-400" />
                      NEXUS AI
                    </span>
                    <span>{msg.timestamp}</span>
                    {msg.difficulty && (
                      <span className="px-1 rounded bg-slate-900 border border-slate-700 text-slate-400">
                        {msg.difficulty.toUpperCase()}
                      </span>
                    )}
                  </>
                )}
              </div>

              {/* Chat Bubble */}
              <div 
                className={`p-3 rounded-2xl max-w-[92%] leading-relaxed text-[11px] border transition-all ${
                  isUser
                    ? 'bg-cyan-950/70 border-cyan-400/50 text-white shadow-[0_0_12px_rgba(0,240,255,0.2)] rounded-br-xs'
                    : 'bg-[#040814]/90 border-[#00f0ff]/20 text-slate-200 rounded-bl-xs shadow-inner'
                }`}
              >
                {/* Assistant Tools Used Header */}
                {!isUser && msg.toolsUsed && msg.toolsUsed.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2 pb-1.5 border-b border-slate-800">
                    {msg.toolsUsed.map((tool, idx) => (
                      <span 
                        key={idx}
                        className="px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-400/30 text-[8px] text-cyan-300 font-bold flex items-center gap-1"
                      >
                        <Zap className="w-2 h-2 text-cyan-400" />
                        <span>MCP: {tool}</span>
                      </span>
                    ))}
                  </div>
                )}

                {/* Message Content */}
                <p className="whitespace-pre-wrap">{msg.content}</p>

                {/* Assistant Action Triggers (Module 4: Agent Routing & Tool Calls) */}
                {!isUser && msg.actionTriggers && msg.actionTriggers.length > 0 && (
                  <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex flex-wrap gap-1.5">
                    {msg.actionTriggers.map((act, idx) => (
                      <button
                        key={idx}
                        onClick={() => onTriggerAction && onTriggerAction(act.action, act.payload)}
                        className="px-2 py-1 rounded-lg bg-cyan-950/90 hover:bg-cyan-900 border border-cyan-400/50 hover:border-cyan-300 text-cyan-200 text-[9px] font-bold flex items-center gap-1 transition-all cursor-pointer shadow-sm hover:scale-102"
                      >
                        {act.action === 'OPEN_MULTIMODAL' && <Eye className="w-2.5 h-2.5 text-cyan-400" />}
                        {act.action === 'OPEN_CODE' && <Code2 className="w-2.5 h-2.5 text-emerald-400" />}
                        {act.action === 'OPEN_CANVAS' && <Layers className="w-2.5 h-2.5 text-purple-400" />}
                        {act.action === 'OPEN_VIDEO' && <Film className="w-2.5 h-2.5 text-amber-400" />}
                        <span>{act.label}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Real-time Token Streaming Indicator */}
        {isStreaming && (
          <div className="flex items-center gap-2 p-2 rounded-xl bg-cyan-950/50 border border-cyan-500/30 text-[10px] text-cyan-300">
            <Zap className="w-3 h-3 text-cyan-400 animate-spin" />
            <span>NEXUS synthesizing cognitive stream...</span>
          </div>
        )}
      </div>
    </div>
  );
};
