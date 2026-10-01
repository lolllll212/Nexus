import React, { useRef, useEffect, useState } from 'react';
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
  Eye,
  Code2,
  Layers,
  Film,
  Send,
  Trash2,
  HelpCircle,
  Activity,
  Compass
} from 'lucide-react';
import { ConversationalMessage, TaskDifficulty } from '../types';

interface ConversationalStreamProps {
  messages: ConversationalMessage[];
  isOpen: boolean;
  onToggleOpen: () => void;
  onTriggerAction?: (action: string, payload?: any) => void;
  isStreaming?: boolean;
  onSendMessage?: (message: string) => void;
  onClearMessages?: () => void;
}

// Simple parser for markdown-like formatting (bold, code, lists)
function renderFormattedText(text: string) {
  const lines = text.split('\n');
  return lines.map((line, lIdx) => {
    // Check if bullet point
    const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('* ');
    const content = isBullet ? line.trim().substring(2) : line;

    // Parse bold **text** and inline `code`
    const parts = content.split(/(\*\*.*?\*\*|`.*?`)/g);

    const renderedLine = parts.map((part, pIdx) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={pIdx} className="font-bold text-cyan-200">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={pIdx} className="px-1.5 py-0.5 rounded bg-slate-900 border border-cyan-500/30 text-cyan-300 font-mono text-[10px]">
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });

    if (isBullet) {
      return (
        <div key={lIdx} className="flex items-start gap-1.5 my-0.5 pl-1">
          <span className="text-cyan-400 mt-0.5">•</span>
          <span className="flex-1">{renderedLine}</span>
        </div>
      );
    }

    return (
      <span key={lIdx}>
        {renderedLine}
        {lIdx < lines.length - 1 && <br />}
      </span>
    );
  });
}

export const ConversationalStream: React.FC<ConversationalStreamProps> = ({
  messages,
  isOpen,
  onToggleOpen,
  onTriggerAction,
  isStreaming = false,
  onSendMessage,
  onClearMessages,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [inputVal, setInputVal] = useState('');

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = inputVal.trim();
    if (!query) return;
    if (onSendMessage) {
      onSendMessage(query);
    }
    setInputVal('');
  };

  const handleQuickChip = (chipText: string) => {
    if (onSendMessage) {
      onSendMessage(chipText);
    }
  };

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
    <div 
      className={`fixed bottom-24 right-6 z-30 flex flex-col glass-obsidian rounded-2xl border border-[#00f0ff]/40 shadow-[0_16px_40px_rgba(0,0,0,0.85),0_0_25px_rgba(0,240,255,0.2)] font-mono select-none overflow-hidden animate-fade-in transition-all duration-300 ${
        isExpanded ? 'w-[680px] h-[640px] max-w-[94vw] max-h-[85vh]' : 'w-96 md:w-[440px] h-[500px] max-h-[75vh]'
      }`}
    >
      {/* ── Conversational Stream Header ─────────────────────────────────────── */}
      <div className="p-3 bg-[#060a16]/95 border-b border-[#00f0ff]/20 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-cyan-950/80 border border-cyan-400/40 flex items-center justify-center">
            <Terminal className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-black tracking-widest text-cyan-200 uppercase">
                CONVERSATIONAL CORTEX
              </span>
              <span className="px-1.5 py-0.2 rounded bg-cyan-950/80 border border-cyan-400/30 text-[8px] text-cyan-300 font-bold">
                v2.4
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {onClearMessages && messages.length > 1 && (
            <button
              onClick={onClearMessages}
              title="Clear messages"
              className="p-1 rounded-md text-slate-400 hover:text-red-400 hover:bg-slate-800/60 transition-colors cursor-pointer"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}

          <button
            onClick={() => setIsExpanded((prev) => !prev)}
            title={isExpanded ? "Collapse view" : "Expand view"}
            className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors cursor-pointer"
          >
            {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={onToggleOpen}
            title="Minimize chat"
            className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── Quick Action Chips Header ────────────────────────────────────────── */}
      <div className="px-3 py-1.5 bg-[#03060f]/80 border-b border-slate-800 flex items-center gap-1.5 overflow-x-auto shrink-0 scrollbar-none">
        <button
          onClick={() => handleQuickChip('hi')}
          className="px-2 py-0.5 rounded-md bg-cyan-950/60 hover:bg-cyan-900 border border-cyan-400/30 text-[9px] text-cyan-300 hover:text-white font-semibold transition-all cursor-pointer shrink-0"
        >
          👋 Greeting
        </button>
        <button
          onClick={() => handleQuickChip('what tools do you have?')}
          className="px-2 py-0.5 rounded-md bg-slate-900/80 hover:bg-cyan-950 border border-slate-800 hover:border-cyan-400/40 text-[9px] text-slate-300 hover:text-cyan-200 transition-all cursor-pointer shrink-0"
        >
          🛠️ List Tools
        </button>
        <button
          onClick={() => handleQuickChip('system health')}
          className="px-2 py-0.5 rounded-md bg-slate-900/80 hover:bg-cyan-950 border border-slate-800 hover:border-cyan-400/40 text-[9px] text-slate-300 hover:text-cyan-200 transition-all cursor-pointer shrink-0"
        >
          ⚡ System Health
        </button>
        <button
          onClick={() => handleQuickChip('open code compiler')}
          className="px-2 py-0.5 rounded-md bg-slate-900/80 hover:bg-emerald-950 border border-slate-800 hover:border-emerald-400/40 text-[9px] text-emerald-400/80 hover:text-emerald-300 transition-all cursor-pointer shrink-0"
        >
          &lt;/&gt; Code Sandbox
        </button>
      </div>

      {/* ── Message Feed ────────────────────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3.5 space-y-3.5 text-xs">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isCopied = copiedId === msg.id;

          return (
            <div 
              key={msg.id} 
              className={`flex flex-col group ${isUser ? 'items-end' : 'items-start'}`}
            >
              {/* Header label & timestamp */}
              <div className="flex items-center gap-1.5 mb-1 text-[8.5px] text-slate-400">
                {isUser ? (
                  <>
                    <span>{msg.timestamp}</span>
                    <span className="text-cyan-400 font-bold uppercase tracking-wider">OPERATOR</span>
                  </>
                ) : (
                  <>
                    <span className="text-cyan-300 font-bold flex items-center gap-1 uppercase tracking-wider">
                      <Sparkles className="w-2.5 h-2.5 text-cyan-400" />
                      NEXUS AI
                    </span>
                    <span>{msg.timestamp}</span>
                    {msg.difficulty && (
                      <span className="px-1.5 py-0.2 rounded bg-slate-900 border border-slate-700 text-slate-400 font-semibold">
                        {msg.difficulty.toUpperCase()}
                      </span>
                    )}
                  </>
                )}
              </div>

              {/* Chat Bubble Container */}
              <div className="relative max-w-[92%]">
                <div 
                  className={`p-3 rounded-2xl leading-relaxed text-[11px] border transition-all ${
                    isUser
                      ? 'bg-cyan-950/70 border-cyan-400/50 text-white shadow-[0_0_12px_rgba(0,240,255,0.2)] rounded-br-xs'
                      : 'bg-[#040814]/90 border-[#00f0ff]/25 text-slate-200 rounded-bl-xs shadow-inner'
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
                          <span>{tool.startsWith('MCP:') ? tool : `TOOL: ${tool}`}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Formatted Message Content */}
                  <div className="whitespace-pre-wrap font-sans text-[11.5px] leading-relaxed">
                    {renderFormattedText(msg.content)}
                  </div>

                  {/* Assistant Action Triggers */}
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

                {/* Copy button */}
                <button
                  onClick={() => handleCopy(msg.id, msg.content)}
                  title="Copy message"
                  className={`absolute -bottom-2 ${isUser ? '-left-6' : '-right-6'} opacity-0 group-hover:opacity-100 p-1 rounded bg-slate-900/90 border border-slate-800 text-slate-400 hover:text-white transition-opacity cursor-pointer shadow-sm`}
                >
                  {isCopied ? <Check className="w-2.5 h-2.5 text-emerald-400" /> : <Copy className="w-2.5 h-2.5" />}
                </button>
              </div>
            </div>
          );
        })}

        {/* Real-time Token Streaming Indicator */}
        {isStreaming && (
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-[10.5px] text-cyan-300 shadow-[0_0_12px_rgba(0,240,255,0.2)] animate-pulse">
            <Zap className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
            <span>NEXUS synthesizing cognitive stream...</span>
          </div>
        )}
      </div>

      {/* ── Inline Input Field Form ─────────────────────────────────────────── */}
      <form 
        onSubmit={handleSend}
        className="p-2.5 bg-[#040713]/95 border-t border-[#00f0ff]/20 flex items-center gap-1.5 shrink-0"
      >
        <input
          ref={inputRef}
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          placeholder="Ask NEXUS or dispatch command..."
          className="flex-1 bg-slate-950/90 border border-slate-800 focus:border-cyan-400/60 rounded-xl px-3 py-1.5 text-xs text-white placeholder:text-slate-500 font-mono focus:outline-none transition-colors"
        />

        <button
          type="submit"
          disabled={!inputVal.trim()}
          className={`p-2 rounded-xl text-xs font-bold transition-all ${
            inputVal.trim()
              ? 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-[0_0_10px_rgba(0,240,255,0.3)] cursor-pointer active:scale-95'
              : 'bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed'
          }`}
          title="Send Message"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
};
