import React, { useState } from 'react';
import { 
  Terminal, 
  Send, 
  Mic, 
  Paperclip, 
  Globe, 
  Code, 
  Search, 
  Sparkles,
  Zap,
  CheckCircle2,
  Cpu,
  Loader2,
  Volume2
} from 'lucide-react';
import { AgentStatus } from '../types';

interface CommandCenterProps {
  onExecuteCommand: (query: string, actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH') => void;
  onOpenClaudeStudio: () => void;
  onOpenResearchMode: (topic?: string) => void;
  onOpenVoiceCortex: () => void;
  agentStatus?: AgentStatus;
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onExecuteCommand,
  onOpenClaudeStudio,
  onOpenResearchMode,
  onOpenVoiceCortex,
  agentStatus = 'idle',
}) => {
  const [query, setQuery] = useState('');
  const [isInjecting, setIsInjecting] = useState(false);

  // FIX 3: Prevent state race conditions - lock input & triggers while agent is resolving
  const isBusy = agentStatus === 'thinking' || agentStatus === 'speaking' || isInjecting;

  const promptChips = [
    { label: '✦ Transcode Image/Video for Non-Vision LLM', type: 'CODE' as const },
    { label: 'Research AI Agent Architectures', type: 'RESEARCH' as const },
    { label: 'Analyze GitHub Repository', type: 'CODE' as const },
    { label: 'Find Connections Between Projects', type: 'GRAPH' as const },
    { label: 'Build Workflow to Monitor Topic', type: 'WORKFLOW' as const },
    { label: 'Remember Kernel Hardening Audit', type: 'MEMORY' as const },
  ];

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || isBusy) return;

    setIsInjecting(true);
    let actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH' = 'GRAPH';
    const lower = query.toLowerCase();
    if (lower.includes('research')) actionType = 'RESEARCH';
    else if (lower.includes('workflow') || lower.includes('pipeline')) actionType = 'WORKFLOW';
    else if (lower.includes('code') || lower.includes('analyze') || lower.includes('git')) actionType = 'CODE';
    else if (lower.includes('remember') || lower.includes('memory')) actionType = 'MEMORY';

    onExecuteCommand(query, actionType);

    setTimeout(() => {
      setQuery('');
      setIsInjecting(false);
    }, 600);
  };

  const getPlaceholderText = () => {
    if (agentStatus === 'thinking') {
      return '⚡ NEXUS is resolving task... Input locked to prevent race collision';
    }
    if (agentStatus === 'speaking') {
      return '🔊 NEXUS vocal speech active... Microphone & input locked';
    }
    if (agentStatus === 'listening') {
      return '🎙️ Voice Cortex listening... Speak your command or hotkey M to stop';
    }
    return 'Message NEXUS...';
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-2 w-[92vw] max-w-4xl select-none font-mono">
      {/* ── Quick Prompt Chips ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-1 px-1">
        {promptChips.map((chip, idx) => (
          <button
            key={idx}
            disabled={isBusy}
            onClick={() => {
              if (isBusy) return;
              setQuery(chip.label);
              onExecuteCommand(chip.label, chip.type);
            }}
            className={`px-2.5 py-1 rounded-full text-[10px] border transition-all backdrop-blur-md shrink-0 ${
              isBusy
                ? 'bg-slate-950/40 border-slate-900 text-slate-600 cursor-not-allowed opacity-50'
                : 'bg-slate-950/80 hover:bg-cyan-950/70 border-slate-800 hover:border-cyan-400/40 text-slate-400 hover:text-cyan-300 cursor-pointer'
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* ── Main AI Command Terminal Bar ────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className={`w-full flex items-center gap-2 p-2 rounded-2xl glass-obsidian border transition-all duration-300 ${
          agentStatus === 'thinking'
            ? 'border-amber-400/70 bg-[#0a0f1d]/95 shadow-[0_12px_48px_rgba(0,0,0,0.95),0_0_35px_rgba(255,170,0,0.35)]'
            : agentStatus === 'speaking'
            ? 'border-cyan-400 bg-[#0a0f1d]/95 shadow-[0_12px_48px_rgba(0,0,0,0.95),0_0_35px_rgba(0,240,255,0.4)]'
            : agentStatus === 'listening'
            ? 'border-[#00ff88]/80 bg-[#0a0f1d]/95 shadow-[0_12px_48px_rgba(0,0,0,0.95),0_0_35px_rgba(0,255,136,0.35)]'
            : 'border-[#00f0ff]/30 bg-[#0a0f1d]/90 shadow-[0_12px_48px_rgba(0,0,0,0.85),0_0_25px_rgba(0,240,255,0.2)] hover:border-[#00f0ff]/50'
        }`}
      >
        {/* Terminal Icon & Status Badge */}
        <div className="flex items-center gap-2 pl-2">
          {agentStatus === 'thinking' ? (
            <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
          ) : agentStatus === 'speaking' ? (
            <Volume2 className="w-4 h-4 text-amber-400 animate-pulse" />
          ) : agentStatus === 'listening' ? (
            <Mic className="w-4 h-4 text-cyan-400 animate-bounce" />
          ) : (
            <Terminal className="w-4 h-4 text-cyan-400" />
          )}

          {/* Explicit Agent Status Indicator */}
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
              agentStatus === 'thinking'
                ? 'bg-purple-950 text-purple-300 border border-purple-500/40 animate-pulse'
                : agentStatus === 'speaking'
                ? 'bg-amber-950 text-amber-300 border border-amber-500/40 animate-pulse'
                : agentStatus === 'listening'
                ? 'bg-cyan-950 text-cyan-300 border border-cyan-400/40'
                : 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/30'
            }`}
          >
            {agentStatus}
          </span>
        </div>

        {/* Input Field - Disabled while agent is thinking or speaking */}
        <input
          type="text"
          value={query}
          disabled={isBusy}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={getPlaceholderText()}
          className={`flex-1 bg-transparent text-xs font-mono text-white placeholder:text-slate-500 focus:outline-none transition-opacity ${
            isBusy ? 'opacity-60 cursor-not-allowed' : 'opacity-100'
          }`}
        />

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={isBusy}
            onClick={onOpenVoiceCortex}
            className={`p-2 rounded-xl transition-colors ${
              isBusy
                ? 'text-slate-600 cursor-not-allowed'
                : 'text-slate-400 hover:text-cyan-300 hover:bg-slate-900 cursor-pointer'
            }`}
            title={isBusy ? 'Microphone locked while agent is active' : 'Voice Input (Hotkey: M)'}
          >
            <Mic className="w-4 h-4" />
          </button>

          <button
            type="button"
            disabled={isBusy}
            onClick={() => onExecuteCommand('Attach Local File to Graph', 'MEMORY')}
            className={`p-2 rounded-xl transition-colors ${
              isBusy
                ? 'text-slate-600 cursor-not-allowed'
                : 'text-slate-400 hover:text-cyan-300 hover:bg-slate-900 cursor-pointer'
            }`}
            title="Attach Document / Node"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <button
            type="button"
            disabled={isBusy}
            onClick={() => onOpenResearchMode(query || 'Autonomous Web Crawl')}
            className={`p-2 rounded-xl transition-colors ${
              isBusy
                ? 'text-slate-600 cursor-not-allowed'
                : 'text-slate-400 hover:text-cyan-300 hover:bg-slate-900 cursor-pointer'
            }`}
            title="Web Research"
          >
            <Globe className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={onOpenClaudeStudio}
            className="p-2 rounded-xl text-slate-400 hover:text-amber-400 hover:bg-amber-950/40 transition-colors cursor-pointer"
            title="Launch Claude Studio"
          >
            <Code className="w-4 h-4" />
          </button>

          <button
            type="submit"
            disabled={!query.trim() || isBusy}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md ${
              isBusy
                ? 'bg-slate-900 text-slate-500 border border-slate-800 cursor-not-allowed opacity-70'
                : query.trim()
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-black hover:from-cyan-400 hover:to-blue-500 shadow-[0_0_15px_rgba(0,240,255,0.4)] cursor-pointer'
                : 'bg-slate-900 text-slate-600 border border-slate-800 cursor-not-allowed'
            }`}
          >
            {agentStatus === 'thinking' ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>THINKING</span>
              </>
            ) : agentStatus === 'speaking' ? (
              <>
                <Volume2 className="w-3.5 h-3.5 animate-pulse" />
                <span>SPEAKING</span>
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5" />
                <span>{isInjecting ? 'SENDING' : 'SEND'}</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
