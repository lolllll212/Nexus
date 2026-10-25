import React, { useEffect, useRef } from 'react';
import { Telescope, ImagePlus, Search, Music, ArrowUp } from 'lucide-react';

export type ConsoleMode = 'chat' | 'research' | 'image' | 'search' | 'music';
export type ConsoleStatus = 'idle' | 'thinking' | 'streaming';

interface QueryConsoleProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string, mode: ConsoleMode) => void;
  status: ConsoleStatus;
  statusDetail: string;
  activeMode: ConsoleMode;
  onModeChange: (mode: ConsoleMode) => void;
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
}

const CHIPS: Array<{
  id: ConsoleMode;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  hint: string;
  base: string;
  active: string;
}> = [
  {
    id: 'research',
    label: 'Deep Research',
    icon: Telescope,
    hint: 'Background multi-hop research execution stream → POST /api/research/execute',
    base: 'border-cyan-400/40 text-cyan-200/90 hover:bg-cyan-400/10 hover:border-cyan-300/70',
    active:
      'border-cyan-300/90 text-cyan-100 bg-cyan-400/15 shadow-[0_0_16px_rgba(34,211,238,0.35)]',
  },
  {
    id: 'image',
    label: 'Make an Image',
    icon: ImagePlus,
    hint: 'Procedural art synthesis → POST /api/workspace/image',
    base: 'border-slate-600/70 text-slate-300 hover:bg-slate-700/40 hover:border-slate-500',
    active: 'border-white/70 text-white bg-white/15 shadow-[0_0_16px_rgba(255,255,255,0.18)]',
  },
  {
    id: 'search',
    label: 'Search',
    icon: Search,
    hint: 'Unified multi-modal search → POST /api/workspace/search',
    base: 'border-slate-600/70 text-slate-300 hover:bg-slate-700/40 hover:border-slate-500',
    active: 'border-white/70 text-white bg-white/15 shadow-[0_0_16px_rgba(255,255,255,0.18)]',
  },
  {
    id: 'music',
    label: 'Create music',
    icon: Music,
    hint: 'Generative audio cortex → POST /api/workspace/music',
    base: 'border-slate-600/70 text-slate-300 hover:bg-slate-700/40 hover:border-slate-500',
    active: 'border-white/70 text-white bg-white/15 shadow-[0_0_16px_rgba(255,255,255,0.18)]',
  },
];

const MODE_HINTS: Record<ConsoleMode, string> = {
  chat: "Example: 'Explain quantum computing in simple terms'",
  research: 'Example: \'Research the latest breakthroughs in fusion energy\'',
  image: "Example: 'Aurora over a neural skyline at dusk'",
  search: "Example: 'quantum computing notes'",
  music: "Example: 'A dreamy focus track for deep work'",
};

/**
 * SCREEN 2 — Floating Query Console.
 * High-contrast dark graphite pill (#0B0F19) with a textarea and four
 * functional action chips, each wired to a real backend route. While the
 * server thinks / streams, a dual-layer cyan + violet pulse aura visualises
 * the live THINKING / STREAMING state.
 */
export const QueryConsole: React.FC<QueryConsoleProps> = ({
  value,
  onChange,
  onSubmit,
  status,
  statusDetail,
  activeMode,
  onModeChange,
  textareaRef,
}) => {
  const localRef = useRef<HTMLTextAreaElement | null>(null);
  const ref = textareaRef ?? localRef;
  const isLive = status === 'thinking' || status === 'streaming';

  // Auto-grow the textarea as the operator types.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [value, ref]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !isLive) onSubmit(value.trim(), activeMode);
    }
  };

  const handleChipClick = (mode: ConsoleMode) => {
    onModeChange(mode);
    // With text ready, the chip fires the backend route immediately.
    if (value.trim() && !isLive) onSubmit(value.trim(), mode);
    else ref.current?.focus();
  };

  return (
    <div className="relative">
      {/* ── Dual-layer pulse aura: live THINKING / STREAMING state ─────────── */}
      {isLive && (
        <>
          <div
            aria-hidden
            className={`pointer-events-none absolute -inset-1.5 rounded-[2.25rem] bg-cyan-400/30 blur-2xl ${
              status === 'streaming' ? 'animate-[nxs-aura-fast_1.4s_ease-in-out_infinite]' : 'animate-[nxs-aura-cyan_2.4s_ease-in-out_infinite]'
            }`}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-3.5 rounded-[2.75rem] bg-violet-500/30 blur-3xl animate-[nxs-aura-violet_2.4s_ease-in-out_infinite]"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-6 rounded-[3.25rem] bg-cyan-400/10 blur-3xl animate-[nxs-aura-violet_3.2s_ease-in-out_0.4s_infinite]"
          />
        </>
      )}

      {/* ── Live state badge ────────────────────────────────────────────────── */}
      <div
        className={`pointer-events-none absolute -top-10 left-3 flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#0B0F19]/95 backdrop-blur border text-[10px] font-bold tracking-[0.22em] uppercase nxs-mono transition-all duration-300 ${
          isLive
            ? 'opacity-100 translate-y-0 border-cyan-400/40 shadow-[0_0_20px_rgba(34,211,238,0.25)]'
            : 'opacity-0 translate-y-1 border-transparent'
        } ${status === 'streaming' ? 'text-violet-200' : 'text-cyan-200'}`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            status === 'streaming' ? 'bg-violet-400 animate-ping' : 'bg-cyan-400 animate-pulse'
          }`}
        />
        {status === 'streaming' ? 'Streaming' : 'Thinking'}
        {statusDetail && (
          <span className="text-slate-500 tracking-[0.08em] normal-case font-medium">· {statusDetail}</span>
        )}
      </div>

      {/* ── The graphite cockpit ────────────────────────────────────────────── */}
      <div
        className={`relative bg-[#0B0F19] rounded-[1.9rem] border transition-all duration-300 shadow-[0_28px_70px_-16px_rgba(11,15,25,0.6),0_4px_14px_-6px_rgba(11,15,25,0.4)] ${
          isLive
            ? 'border-cyan-400/40 shadow-[0_28px_80px_-14px_rgba(34,211,238,0.35),0_4px_14px_-6px_rgba(139,92,246,0.3)]'
            : 'border-white/10 hover:border-white/20'
        }`}
        role="form"
        aria-label="NEXUS multi-modal query console"
      >
        {/* Streaming progress shimmer */}
        {isLive && (
          <div className="absolute inset-x-6 top-0 h-[2px] overflow-hidden rounded-full">
            <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-transparent via-cyan-300 to-violet-400 animate-[nxs-shimmer_1.6s_linear_infinite]" />
          </div>
        )}

        <div className="flex items-end gap-2.5 pl-4 pr-3 py-3">
          {/* Status orb */}
          <div className="pb-2.5 pl-0.5 shrink-0" title={isLive ? `Server state: ${status.toUpperCase()}` : 'Server state: IDLE'}>
            <span
              className={`block w-2.5 h-2.5 rounded-full ${
                isLive
                  ? 'bg-gradient-to-br from-cyan-300 to-violet-400 animate-[nxs-orb-live_1.6s_ease-in-out_infinite]'
                  : 'bg-slate-600 animate-[nxs-orb-idle_3.2s_ease-in-out_infinite]'
              }`}
            />
          </div>

          {/* Text entry area */}
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder={activeMode === 'chat' ? MODE_HINTS.chat : MODE_HINTS[activeMode]}
            spellCheck={false}
            aria-label="Query the NEXUS cortex"
            className="flex-1 resize-none bg-transparent text-slate-100 placeholder:text-slate-500 text-[14px] leading-6 py-2 outline-none nxs-scroll max-h-[132px] selection:bg-cyan-400/30"
          />

          {/* Integrated action chips — backend routes */}
          <div className="flex items-center gap-1.5 pb-0.5 shrink-0">
            {CHIPS.map((chip) => {
              const Icon = chip.icon;
              const isActive = activeMode === chip.id;
              return (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => handleChipClick(chip.id)}
                  disabled={isLive}
                  title={chip.hint}
                  aria-pressed={isActive}
                  className={`nxs-chip hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-[11px] font-semibold whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer ${
                    isActive ? chip.active : chip.base
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" strokeWidth={1.9} />
                  <span>{chip.label}</span>
                  {/* Deep Research: background execution stream indicator */}
                  {chip.id === 'research' && isActive && isLive && (
                    <span className="flex gap-[2px] items-end h-3">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="w-[2px] rounded-full bg-cyan-300 animate-pulse"
                          style={{ height: `${5 + i * 3}px`, animationDelay: `${i * 0.18}s` }}
                        />
                      ))}
                    </span>
                  )}
                </button>
              );
            })}

            {/* Submit */}
            <button
              type="button"
              onClick={() => value.trim() && !isLive && onSubmit(value.trim(), activeMode)}
              disabled={!value.trim() || isLive}
              aria-label="Run query"
              className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-all cursor-pointer ${
                value.trim() && !isLive
                  ? 'bg-white text-slate-900 hover:bg-cyan-200 hover:shadow-[0_0_18px_rgba(34,211,238,0.5)]'
                  : 'bg-white/10 text-slate-600 cursor-not-allowed'
              }`}
            >
              <ArrowUp className="w-4 h-4" strokeWidth={2.4} />
            </button>
          </div>
        </div>

        {/* Mobile chip row (chips hidden inline on very narrow screens) */}
        <div className="sm:hidden flex items-center gap-1.5 px-4 pb-3 -mt-0.5 overflow-x-auto nxs-scroll">
          {CHIPS.map((chip) => {
            const Icon = chip.icon;
            const isActive = activeMode === chip.id;
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => handleChipClick(chip.id)}
                disabled={isLive}
                className={`nxs-chip shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-[11px] font-semibold disabled:opacity-60 cursor-pointer ${
                  isActive ? chip.active : chip.base
                }`}
              >
                <Icon className="w-3.5 h-3.5" strokeWidth={1.9} />
                <span>{chip.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Route caption */}
      <div className="mt-2 flex items-center justify-between px-2 text-[10px] nxs-mono text-slate-400">
        <span>
          {activeMode === 'chat' && <>↵ streams via <span className="text-slate-500">POST /v1/chat/stream</span></>}
          {activeMode === 'research' && <>→ <span className="text-cyan-600">POST /api/research/execute</span> · background stream</>}
          {activeMode === 'image' && <>→ <span className="text-slate-500">POST /api/workspace/image</span></>}
          {activeMode === 'search' && <>→ <span className="text-slate-500">POST /api/workspace/search</span></>}
          {activeMode === 'music' && <>→ <span className="text-slate-500">POST /api/workspace/music</span></>}
        </span>
        <span className="hidden sm:inline text-slate-400">⏎ run · ⇧⏎ newline</span>
      </div>
    </div>
  );
};
