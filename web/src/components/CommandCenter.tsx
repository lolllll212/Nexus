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
  Cpu
} from 'lucide-react';

interface CommandCenterProps {
  onExecuteCommand: (query: string, actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH') => void;
  onOpenClaudeStudio: () => void;
  onOpenResearchMode: (topic?: string) => void;
  onOpenVoiceCortex: () => void;
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onExecuteCommand,
  onOpenClaudeStudio,
  onOpenResearchMode,
  onOpenVoiceCortex,
}) => {
  const [query, setQuery] = useState('');
  const [isInjecting, setIsInjecting] = useState(false);

  const promptChips = [
    { label: 'Research AI Agent Architectures', type: 'RESEARCH' as const },
    { label: 'Analyze GitHub Repository', type: 'CODE' as const },
    { label: 'Find Connections Between Projects', type: 'GRAPH' as const },
    { label: 'Build Workflow to Monitor Topic', type: 'WORKFLOW' as const },
    { label: 'Remember Kernel Hardening Audit', type: 'MEMORY' as const },
  ];

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

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
    }, 800);
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-2 w-[92vw] max-w-4xl select-none font-mono">
      {/* ── Quick Prompt Chips ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-1 px-1">
        {promptChips.map((chip, idx) => (
          <button
            key={idx}
            onClick={() => {
              setQuery(chip.label);
              onExecuteCommand(chip.label, chip.type);
            }}
            className="px-2.5 py-1 rounded-full text-[10px] bg-slate-950/80 hover:bg-cyan-950/70 border border-slate-800 hover:border-cyan-400/40 text-slate-400 hover:text-cyan-300 transition-all backdrop-blur-md shrink-0 cursor-pointer"
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* ── Main AI Command Terminal Bar ────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className="w-full flex items-center gap-2 p-2 rounded-2xl glass-panel border border-cyan-500/30 bg-slate-950/90 backdrop-blur-2xl shadow-[0_12px_48px_rgba(0,0,0,0.8),0_0_25px_rgba(0,240,255,0.2)]"
      >
        <div className="p-2 text-cyan-400">
          <Terminal className="w-5 h-5" />
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask NEXUS anything or give it an autonomous task..."
          className="flex-1 bg-transparent text-xs font-mono text-white placeholder:text-slate-500 focus:outline-none"
        />

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onOpenVoiceCortex}
            className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
            title="Voice Input"
          >
            <Mic className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={() => onExecuteCommand('Attach Local File to Graph', 'MEMORY')}
            className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
            title="Attach Document / Node"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={() => onOpenResearchMode(query || 'Autonomous Web Crawl')}
            className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
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
            disabled={!query.trim() || isInjecting}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md cursor-pointer ${
              query.trim()
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-black hover:from-cyan-400 hover:to-blue-500 shadow-[0_0_15px_rgba(0,240,255,0.4)]'
                : 'bg-slate-900 text-slate-600 border border-slate-800'
            }`}
          >
            <Send className="w-3.5 h-3.5" />
            <span>{isInjecting ? 'Injecting...' : 'EXECUTE'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
