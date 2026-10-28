import React, { useEffect, useRef, useState } from 'react';
import { Telescope, ImagePlus, Search, Music, ArrowUp, Paperclip, Square, X, ScanSearch, FileText, Film, AudioLines, File as FileIcon } from 'lucide-react';
import { useVoiceInput, WhisperFlowBand, MicButton, RecorderBadge } from './VoiceFlow';

export type ConsoleMode = 'chat' | 'research' | 'image' | 'search' | 'music';
export type ConsoleStatus = 'idle' | 'thinking' | 'streaming';

/** An attachment staged in the console before its multimodal run. */
export interface MediaAttachment {
  id: string;
  file: File;
  kind: 'image' | 'video' | 'audio' | 'doc';
  previewUrl: string | null;
}

const MAX_ATTACHMENTS = 6;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const ACCEPT = 'image/*,video/*,audio/*,.pdf,.txt,.md,.csv,.json';
const DEFAULT_MEDIA_QUESTION = 'Describe this visual scene and identify key elements';

export function classifyFile(file: File): MediaAttachment['kind'] {
  const type = (file.type || '').toLowerCase();
  const name = file.name.toLowerCase();
  if (type.startsWith('image/') || /\.(png|jpe?g|webp|gif|svg|bmp|avif)$/.test(name)) return 'image';
  if (type.startsWith('video/') || /\.(mp4|webm|mov|mkv|avi)$/.test(name)) return 'video';
  if (type.startsWith('audio/') || /\.(mp3|wav|ogg|m4a|flac|aac|webm)$/.test(name)) return 'audio';
  return 'doc';
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface QueryConsoleProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string, mode: ConsoleMode) => void;
  /** Multimodal dispatch — fired by submit when attachments are staged. */
  onSubmitMedia: (attachments: MediaAttachment[], question: string) => void;
  /** Aborts the active cockpit request/stream; the parent owns the controller. */
  onCancel?: () => void;
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

const KIND_ICON: Record<MediaAttachment['kind'], React.ComponentType<{ className?: string; strokeWidth?: number }>> = {
  image: ImagePlus,
  video: Film,
  audio: AudioLines,
  doc: FileText,
};

/**
 * SCREEN 2 — Floating Query Console.
 * High-contrast dark graphite pill (#0B0F19) with a textarea, four functional
 * action chips (each wired to a real backend route), whisper-flow voice input,
 * and multimodal attachments (image / video / audio / docs). While the server
 * thinks / streams, a dual-layer cyan + violet pulse aura visualises the live
 * THINKING / STREAMING state.
 */
export const QueryConsole: React.FC<QueryConsoleProps> = ({
  value,
  onChange,
  onSubmit,
  onSubmitMedia,
  onCancel,
  status,
  statusDetail,
  activeMode,
  onModeChange,
  textareaRef,
}) => {
  const localRef = useRef<HTMLTextAreaElement | null>(null);
  const ref = textareaRef ?? localRef;
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isLive = status === 'thinking' || status === 'streaming';

  const [attachments, setAttachments] = useState<MediaAttachment[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [attachError, setAttachError] = useState('');
  const [interim, setInterim] = useState('');

  /* ── Whisper-flow voice input ─────────────────────────────────────────── */
  const voice = useVoiceInput({
    onInterim: setInterim,
    onFinal: (text) => {
      setInterim('');
      onChange((value ? `${value.trimEnd()} ` : '') + text);
    },
  });
  const listening = voice.state === 'listening' || voice.state === 'starting';
  const hasMedia = attachments.length > 0;

  /* Auto-grow the textarea as the operator types. */
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [value, ref]);

  /* Revoke object URLs when the console unmounts. */
  useEffect(() => {
    return () => {
      attachments.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const incoming = Array.from(files as ArrayLike<File>);
    setAttachError('');
    setAttachments((prev) => {
      const next = [...prev];
      for (const f of incoming) {
        if (next.length >= MAX_ATTACHMENTS) {
          setAttachError(`Up to ${MAX_ATTACHMENTS} attachments per run`);
          break;
        }
        if (f.size > MAX_FILE_BYTES) {
          setAttachError(`${f.name} exceeds the 8 MB perception limit`);
          continue;
        }
        const kind = classifyFile(f);
        next.push({
          id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          file: f,
          kind,
          previewUrl: kind === 'doc' ? null : URL.createObjectURL(f),
        });
      }
      return next;
    });
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((a) => a.id !== id);
    });
  };

  /** Hand the staged attachments to the executor — ownership (and their object
   *  URLs) transfers to the result sheet, so nothing is revoked here. */
  const releaseAttachments = () => {
    setAttachments([]);
    setAttachError('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (e.key === 'Enter' && !e.shiftKey && !nativeEvent.isComposing && nativeEvent.keyCode !== 229) {
      e.preventDefault();
      if (isLive) return;
      if (hasMedia) {
        onSubmitMedia(attachments, value.trim() || DEFAULT_MEDIA_QUESTION);
        releaseAttachments();
      } else if (value.trim()) onSubmit(value.trim(), activeMode);
    }
  };

  const handleSubmit = () => {
    if (isLive) return;
    if (hasMedia) {
      onSubmitMedia(attachments, value.trim() || DEFAULT_MEDIA_QUESTION);
      releaseAttachments();
    } else if (value.trim()) {
      onSubmit(value.trim(), activeMode);
    }
  };

  const handleChipClick = (mode: ConsoleMode) => {
    onModeChange(mode);
    // With text ready and no media staged, the chip fires the backend route immediately.
    if (!hasMedia && value.trim() && !isLive) onSubmit(value.trim(), mode);
    else ref.current?.focus();
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from((e.clipboardData?.files ?? []) as ArrayLike<File>);
    if (files.length > 0) {
      e.preventDefault();
      addFiles(files);
    }
  };

  return (
    <div
      className="relative"
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node)) return;
        setDragActive(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragActive(false);
        if (!isLive) addFiles(e.dataTransfer?.files ?? null);
      }}
    >
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
            : dragActive
              ? 'border-cyan-300/70 shadow-[0_28px_80px_-14px_rgba(34,211,238,0.35)]'
              : listening
                ? 'border-cyan-300/50'
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

        {/* Drop overlay */}
        {dragActive && (
          <div className="absolute inset-0 z-20 rounded-[1.9rem] bg-[#0B0F19]/85 backdrop-blur-sm border-2 border-dashed border-cyan-300/70 flex flex-col items-center justify-center gap-1.5 pointer-events-none">
            <ScanSearch className="w-5 h-5 text-cyan-300" strokeWidth={1.8} />
            <span className="text-[12px] font-semibold text-cyan-100">Drop media to attach</span>
            <span className="text-[10px] nxs-mono text-slate-400">image · video · audio · pdf · txt</span>
          </div>
        )}

        {/* ── Voice band + attachments (expands above the input row) ─────── */}
        <div
          className={`overflow-hidden transition-all duration-300 ${
            listening || hasMedia ? 'max-h-[220px] opacity-100' : 'max-h-0 opacity-0'
          }`}
        >
          <div className="px-3 pt-3 flex flex-col gap-2.5">
            {/* Whisper flow — amplitude-reactive ribbon canvas */}
            {listening && (
              <div className="relative">
                <WhisperFlowBand levelRef={voice.levelRef} active={listening} height={58} />
                <div className="absolute inset-0 flex items-center justify-between px-3.5 pointer-events-none">
                  <span className="text-[10px] nxs-mono tracking-[0.18em] uppercase text-cyan-200/80">
                    {voice.state === 'starting' ? 'Opening microphone…' : 'Listening — whisper flow'}
                  </span>
                  {voice.usingRecorder && voice.state === 'listening' && <RecorderBadge />}
                </div>
                {/* Live interim transcript drifting over the flow */}
                {interim && (
                  <div className="absolute -bottom-0.5 left-3.5 right-3.5 flex items-center gap-2 pointer-events-none">
                    <span className="truncate text-[12px] italic text-slate-300/90 animate-[nxs-fade-in_0.35s_ease-out]">
                      {interim}
                    </span>
                    <span className="w-1 h-3.5 bg-cyan-300/80 animate-pulse" />
                  </div>
                )}
              </div>
            )}

            {/* Voice notes / honest unavailability */}
            {voice.note && (
              <div className="text-[11px] nxs-mono text-amber-200/80 px-1">{voice.note}</div>
            )}

            {/* Attachment chips */}
            {hasMedia && (
              <div className="flex flex-wrap gap-2 px-0.5">
                {attachments.map((att) => {
                  const Icon = KIND_ICON[att.kind];
                  return (
                    <div
                      key={att.id}
                      className="group relative flex items-center gap-2 pl-1.5 pr-2.5 py-1.5 rounded-xl bg-white/[0.05] border border-white/10 hover:border-cyan-300/40 transition-colors animate-[nxs-bus-in_0.3s_ease-out]"
                    >
                      {att.kind === 'image' && att.previewUrl ? (
                        <img
                          src={att.previewUrl}
                          alt={att.file.name}
                          className="w-8 h-8 rounded-lg object-cover border border-white/10"
                        />
                      ) : att.kind === 'video' && att.previewUrl ? (
                        <video src={att.previewUrl} className="w-8 h-8 rounded-lg object-cover border border-white/10" muted preload="metadata" />
                      ) : (
                        <span className="w-8 h-8 rounded-lg bg-cyan-400/10 border border-cyan-300/20 flex items-center justify-center">
                          <Icon className="w-4 h-4 text-cyan-200" strokeWidth={1.8} />
                        </span>
                      )}
                      <div className="flex flex-col leading-tight max-w-[150px]">
                        <span className="text-[11px] font-medium text-slate-200 truncate">{att.file.name}</span>
                        <span className="text-[9.5px] nxs-mono uppercase tracking-wider text-slate-500">
                          {att.kind} · {formatBytes(att.file.size)}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeAttachment(att.id)}
                        aria-label={`Remove ${att.file.name}`}
                        className="w-5 h-5 rounded-full bg-white/10 hover:bg-rose-400/80 text-slate-300 hover:text-white transition-colors cursor-pointer flex items-center justify-center"
                      >
                        <X className="w-3 h-3" strokeWidth={2.4} />
                      </button>
                    </div>
                  );
                })}
                {attachments.length >= MAX_ATTACHMENTS && (
                  <span className="self-center text-[10px] nxs-mono text-slate-500">max {MAX_ATTACHMENTS}</span>
                )}
              </div>
            )}
            {attachError && (
              <div className="text-[11px] nxs-mono text-rose-300/80 px-1">{attachError}</div>
            )}
          </div>
        </div>

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
            onPaste={handlePaste}
            rows={1}
            placeholder={
              isLive
                ? 'Nexus is working — draft the next run or stop this one…'
                : hasMedia
                  ? 'Optional: ask a question about the attached media…'
                  : activeMode === 'chat'
                    ? MODE_HINTS.chat
                    : MODE_HINTS[activeMode]
            }
            spellCheck={false}
            aria-label="Query the NEXUS cortex"
            className="flex-1 resize-none bg-transparent text-slate-100 placeholder:text-slate-500 text-[14px] leading-6 py-2 outline-none nxs-scroll max-h-[132px] selection:bg-cyan-400/30"
          />

          {/* Whisper-flow voice input */}
          <MicButton
            state={voice.state}
            levelRef={voice.levelRef}
            disabled={isLive}
            onStart={voice.start}
            onStop={voice.stop}
          />

          {/* Multimodal attachments */}
          <div className="shrink-0 pb-0.5">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLive}
              aria-label="Attach image, video, audio or documents"
              title="Attach media — images & video → POST /api/multimodal/process · audio → POST /api/audio/stt"
              className={`w-9 h-9 rounded-full flex items-center justify-center transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                hasMedia
                  ? 'bg-cyan-400/15 text-cyan-200 border border-cyan-300/50 shadow-[0_0_14px_rgba(34,211,238,0.3)]'
                  : 'bg-white/[0.07] text-slate-300 border border-white/15 hover:bg-white/[0.14] hover:text-cyan-200 hover:border-cyan-300/40'
              }`}
            >
              <Paperclip className="w-4 h-4" strokeWidth={1.9} />
            </button>
          </div>

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

            {isLive && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                aria-label="Stop this run"
                title="Stop this run"
                className="flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-rose-300/50 bg-rose-400/15 px-3 text-[11px] font-bold text-rose-100 transition-colors hover:bg-rose-400/25 cursor-pointer"
              >
                <Square className="h-3.5 w-3.5" strokeWidth={2.2} />
                <span className="hidden md:inline">Stop</span>
              </button>
            )}

            {/* Submit — becomes the multimodal scanner when media is staged */}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isLive || (!hasMedia && !value.trim())}
              aria-label={hasMedia ? 'Analyze attached media' : 'Run query'}
              title={hasMedia ? 'Run the multimodal perception bridge on the attachments' : undefined}
              className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-all cursor-pointer ${
                (hasMedia || value.trim()) && !isLive
                  ? 'bg-white text-slate-900 hover:bg-cyan-200 hover:shadow-[0_0_18px_rgba(34,211,238,0.5)]'
                  : 'bg-white/10 text-slate-600 cursor-not-allowed'
              }`}
            >
              {hasMedia ? <ScanSearch className="w-4 h-4" strokeWidth={2.2} /> : <ArrowUp className="w-4 h-4" strokeWidth={2.4} />}
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
          {hasMedia ? (
            <>
              → <span className="text-cyan-600">POST /api/multimodal/process</span>
              {attachments.some((a) => a.kind === 'audio') && (
                <>
                  {' · '}
                  <span className="text-cyan-600">POST /api/audio/stt</span>
                </>
              )}
              {' '}· perception bridge
            </>
          ) : (
            <>
              {activeMode === 'chat' && <>↵ streams via <span className="text-slate-500">POST /v1/chat/stream</span></>}
              {activeMode === 'research' && <>→ <span className="text-cyan-600">POST /api/research/execute</span> · background stream</>}
              {activeMode === 'image' && <>→ <span className="text-slate-500">POST /api/workspace/image</span></>}
              {activeMode === 'search' && <>→ <span className="text-slate-500">POST /api/workspace/search</span></>}
              {activeMode === 'music' && <>→ <span className="text-slate-500">POST /api/workspace/music</span></>}
            </>
          )}
        </span>
        <span className="hidden sm:inline text-slate-400">⏎ run · ⇧⏎ newline · drag & drop or paste media</span>
      </div>
    </div>
  );
};
