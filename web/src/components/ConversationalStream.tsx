import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  Cpu,
  Download,
  Eye,
  Film,
  Layers,
  Maximize2,
  Minimize2,
  Plus,
  Send,
  Sparkles,
  Square,
  Terminal,
  Volume2,
  X,
  Zap,
} from 'lucide-react';
import { CapabilitiesPanel } from './CapabilitiesPanel';
import { HistoryDrawer } from './HistoryDrawer';
import { ModelPicker } from './ModelPicker';
import { VoiceSettings } from './VoiceSettings';
import { getModelById } from '../data/modelCatalog';
import type { HistorySource } from '../utils/chatHistory';
import {
  speakText,
  stopAnySpeaking,
  type VoicePreferences,
} from '../utils/voiceManager';
import type {
  AgentStatus,
  ChatCapabilities,
  ChatSessionSummary,
  ConversationalMessage,
  ModelCatalog,
} from '../types';

type MaybePromise<T> = T | Promise<T>;

function streamDraftStorageKey(sessionId: string | null): string {
  return `nexus-stream-draft:${sessionId || 'new-session'}`;
}

function loadStreamDraft(sessionId: string | null): string {
  try {
    return window.sessionStorage.getItem(streamDraftStorageKey(sessionId)) || '';
  } catch {
    return '';
  }
}

interface ConversationalStreamProps {
  messages: ConversationalMessage[];
  isOpen: boolean;
  onToggleOpen: () => void;
  onTriggerAction?: (action: string, payload?: any) => void;
  isStreaming?: boolean;
  onSendMessage?: (message: string) => void;
  onStopGeneration?: () => void;
  queuedCount?: number;

  // Model changer
  modelCatalog: ModelCatalog;
  selectedModelId: string;
  onModelChange: (modelId: string) => void;

  // Claude-style capabilities
  capabilities: ChatCapabilities;
  onCapabilitiesChange: (capabilities: ChatCapabilities) => void;

  // Voice output
  voicePreferences: VoicePreferences;
  onVoicePreferencesChange: (preferences: VoicePreferences) => void;
  agentStatus: AgentStatus;
  onAgentStatusChange: (status: AgentStatus) => void;
  speakingMessageId?: string | null;
  onSpeakMessage?: (message: ConversationalMessage) => void;
  onStopSpeaking?: () => void;

  // Server-backed chat history window
  sessions: ChatSessionSummary[];
  historySource: HistorySource;
  currentSessionId: string | null;
  isHistoryLoading?: boolean;
  onRefreshHistory: () => MaybePromise<void>;
  onNewChat: () => MaybePromise<boolean | void>;
  onOpenSession: (sessionId: string) => MaybePromise<boolean | void>;
  onRenameSession: (sessionId: string, title: string) => MaybePromise<boolean | void>;
  onDeleteSession: (sessionId: string) => MaybePromise<boolean | void>;
  onClearHistory?: () => MaybePromise<boolean | void>;
}

type ContentSegment =
  | { type: 'text'; text: string }
  | { type: 'code'; language: string; code: string };

function parseContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const fencePattern = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: content.slice(lastIndex, match.index) });
    }
    segments.push({
      type: 'code',
      language: (match[1] || '').trim() || 'code',
      code: (match[2] || '').replace(/\n$/, ''),
    });
    lastIndex = fencePattern.lastIndex;
    if (match[0].length === 0) fencePattern.lastIndex += 1;
  }

  if (lastIndex < content.length) {
    segments.push({ type: 'text', text: content.slice(lastIndex) });
  }
  return segments.filter((segment) =>
    segment.type === 'code' ? true : segment.text.trim().length > 0,
  );
}

function renderInline(text: string, keyPrefix: string) {
  const tokenPattern =
    /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/|mailto:)[^)\s]+\)|\*[^*]+\*)/g;
  return text.split(tokenPattern).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={key} className="font-bold text-cyan-200">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={key}
          className="rounded border border-cyan-500/30 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = part.match(/^\[([^\]]+)\]\(((?:https?:\/\/|mailto:)[^)\s]+)\)$/);
    if (link) {
      return (
        <a
          key={key}
          href={link[2]}
          target="_blank"
          rel="noreferrer"
          className="font-bold text-cyan-300 underline decoration-cyan-400/40 underline-offset-2 hover:text-cyan-100"
        >
          {link[1]}
        </a>
      );
    }
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

function renderFormattedText(text: string, keyPrefix: string) {
  return text.split('\n').map((line, lineIndex) => {
    const key = `${keyPrefix}-line-${lineIndex}`;
    const trimmed = line.trim();

    if (!trimmed) return <div key={key} className="h-2" />;

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      return (
        <div
          key={key}
          className={`mb-1 mt-2 font-black text-cyan-100 ${
            heading[1].length <= 2 ? 'text-[12px]' : 'text-[11px]'
          }`}
        >
          {renderInline(heading[2], key)}
        </div>
      );
    }

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed
        .slice(1, -1)
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean);
      if (cells.length && cells.every((cell) => /^:?-{3,}:?$/.test(cell))) {
        return <div key={key} className="my-1 border-t border-slate-700" />;
      }
      return (
        <div key={key} className="my-0.5 rounded bg-slate-900/70 px-2 py-1 font-mono text-[9.5px] text-slate-300">
          {cells.map((cell, cellIndex) => (
            <React.Fragment key={`${key}-cell-${cellIndex}`}>
              {cellIndex > 0 && <span className="mx-1.5 text-cyan-500">•</span>}
              {renderInline(cell, `${key}-cell-${cellIndex}`)}
            </React.Fragment>
          ))}
        </div>
      );
    }

    const bullet = trimmed.match(/^[-*+]\s+(.+)$/);
    if (bullet) {
      return (
        <div key={key} className="my-0.5 flex items-start gap-1.5 pl-1">
          <span className="mt-0.5 text-cyan-400">•</span>
          <span className="min-w-0 flex-1">{renderInline(bullet[1], key)}</span>
        </div>
      );
    }

    const numbered = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
    if (numbered) {
      return (
        <div key={key} className="my-0.5 flex items-start gap-1.5 pl-1">
          <span className="mt-0.5 shrink-0 font-black text-cyan-400">{numbered[1]}.</span>
          <span className="min-w-0 flex-1">{renderInline(numbered[2], key)}</span>
        </div>
      );
    }

    if (trimmed.startsWith('>')) {
      return (
        <div key={key} className="my-1 border-l-2 border-cyan-400/50 pl-2 text-slate-300">
          {renderInline(trimmed.replace(/^>\s?/, ''), key)}
        </div>
      );
    }

    return <div key={key}>{renderInline(line, key)}</div>;
  });
}

function cleanThinkingText(thinking: string | undefined, finalContent: string): string {
  if (!thinking) return '';
  let cleaned = thinking.replace(/\r\n/g, '\n');
  const finalAnswerMatch = cleaned.match(/final\s+answer\s*:/i);
  if (finalAnswerMatch?.index !== undefined) {
    cleaned = cleaned.slice(0, finalAnswerMatch.index);
  }
  cleaned = cleaned
    .split('\n')
    .filter((line) => !/TOOL_CALL\s*:/i.test(line))
    .join('\n')
    .replace(/^\s*(thought|thinking|reasoning)\s*:\s*/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  // Some models repeat the final answer as their only "thought" once the
  // FINAL ANSWER envelope is removed; there is nothing useful to reveal then.
  if (cleaned && cleaned === finalContent.trim()) return '';
  return cleaned;
}

function modelDisplayName(modelId: string | undefined, catalog: ModelCatalog): string | null {
  if (!modelId) return null;
  const model = getModelById(catalog.models, modelId);
  if (model) return model.name;
  if (modelId === 'auto') return 'NEXUS Auto';
  return modelId.split('/').filter(Boolean).pop() || modelId;
}

const ArtifactCard: React.FC<{
  artifactId: string;
  language: string;
  code: string;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
  onDownload: (language: string, code: string) => void;
}> = ({ artifactId, language, code, copiedId, onCopy, onDownload }) => {
  const lineCount = code ? code.split('\n').length : 0;
  const isCopied = copiedId === artifactId;
  return (
    <div className="my-2 overflow-hidden rounded-xl border border-cyan-400/30 bg-slate-950/95 shadow-[0_10px_28px_rgba(0,0,0,0.35)]">
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/80 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-cyan-400/30 bg-cyan-950 text-cyan-300">
            <Code2 className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[9px] font-black uppercase tracking-[0.18em] text-cyan-100">
              {language} artifact
            </div>
            <div className="text-[7.5px] font-bold uppercase tracking-wider text-slate-500">
              {lineCount} {lineCount === 1 ? 'line' : 'lines'}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => onCopy(artifactId, code)}
            title="Copy artifact"
            className="flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-slate-300 transition-colors hover:border-cyan-400/50 hover:text-cyan-100 cursor-pointer"
          >
            {isCopied ? <Check className="h-3 w-3 text-emerald-300" /> : <Copy className="h-3 w-3" />}
            {isCopied ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={() => onDownload(language, code)}
            title="Download artifact"
            className="flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-slate-300 transition-colors hover:border-cyan-400/50 hover:text-cyan-100 cursor-pointer"
          >
            <Download className="h-3 w-3" />
            Save
          </button>
        </div>
      </div>
      <pre className="max-h-64 overflow-auto p-3 font-mono text-[10px] leading-relaxed text-slate-100">
        <code>{code}</code>
      </pre>
    </div>
  );
};

export const ConversationalStream: React.FC<ConversationalStreamProps> = ({
  messages,
  isOpen,
  onToggleOpen,
  onTriggerAction,
  isStreaming = false,
  onSendMessage,
  onStopGeneration,
  queuedCount = 0,
  modelCatalog,
  selectedModelId,
  onModelChange,
  capabilities,
  onCapabilitiesChange,
  voicePreferences,
  onVoicePreferencesChange,
  agentStatus,
  onAgentStatusChange,
  speakingMessageId,
  onSpeakMessage,
  onStopSpeaking,
  sessions,
  historySource,
  currentSessionId,
  isHistoryLoading = false,
  onRefreshHistory,
  onNewChat,
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onClearHistory,
}) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const lastAutoScrolledMessageIdRef = useRef<string | null>(null);
  const draftSessionIdRef = useRef(currentSessionId);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [inputVal, setInputVal] = useState(() => loadStreamDraft(currentSessionId));
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [expandedThinkingIds, setExpandedThinkingIds] = useState<Set<string>>(() => new Set());
  const [localSpeakingId, setLocalSpeakingId] = useState<string | null>(null);

  const selectedModel = useMemo(
    () => getModelById(modelCatalog.models, selectedModelId) || modelCatalog.models[0] || null,
    [modelCatalog.models, selectedModelId],
  );

  const effectiveSpeakingId =
    speakingMessageId !== undefined ? speakingMessageId : localSpeakingId;
  const isGenerating = agentStatus === 'thinking' || isStreaming;
  const isBusy = isGenerating || agentStatus === 'listening';

  const scrollToLatest = (behavior: ScrollBehavior = 'smooth') => {
    const element = scrollRef.current;
    if (!element) return;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    element.scrollTo({ top: element.scrollHeight, behavior });
  };

  const handleMessageScroll = () => {
    const element = scrollRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    const nearBottom = distance < 120;
    shouldStickToBottomRef.current = nearBottom;
    setIsNearBottom(nearBottom);
  };

  useEffect(() => {
    if (draftSessionIdRef.current !== currentSessionId) {
      draftSessionIdRef.current = currentSessionId;
      setInputVal(loadStreamDraft(currentSessionId));
      shouldStickToBottomRef.current = true;
      setIsNearBottom(true);
      return;
    }
    try {
      const key = streamDraftStorageKey(currentSessionId);
      if (inputVal) window.sessionStorage.setItem(key, inputVal);
      else window.sessionStorage.removeItem(key);
    } catch {
      // Draft persistence is best-effort in restricted browser contexts.
    }
  }, [currentSessionId, inputVal]);

  useEffect(() => {
    if (!isOpen) return undefined;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    const frame = window.requestAnimationFrame(() => scrollToLatest('auto'));
    return () => window.cancelAnimationFrame(frame);
  }, [currentSessionId, isOpen]);

  useEffect(() => {
    if (!isOpen || !scrollRef.current) return undefined;
    const latest = messages[messages.length - 1];
    const latestId = latest?.id || null;
    const userJustSent =
      latest?.role === 'user' && latestId !== lastAutoScrolledMessageIdRef.current;
    if (userJustSent || shouldStickToBottomRef.current) {
      const frame = window.requestAnimationFrame(() => scrollToLatest('auto'));
      lastAutoScrolledMessageIdRef.current = latestId;
      return () => window.cancelAnimationFrame(frame);
    }
    lastAutoScrolledMessageIdRef.current = latestId;
    return undefined;
  }, [expandedThinkingIds, isOpen, isStreaming, messages]);

  useEffect(() => {
    if (agentStatus !== 'speaking') setLocalSpeakingId(null);
  }, [agentStatus]);

  const handleCopy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
      } catch {
        // Clipboard access can still be blocked by browser policy.
      } finally {
        document.body.removeChild(textarea);
      }
    }
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((current) => (current === id ? null : current)), 2000);
  };

  const handleDownloadArtifact = (language: string, code: string) => {
    const extension = (language || 'txt').toLowerCase().replace(/[^a-z0-9]+/g, '') || 'txt';
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `nexus-artifact.${extension}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const handleSend = (event?: React.FormEvent) => {
    event?.preventDefault();
    const query = inputVal.trim();
    if (!query) return;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    onSendMessage?.(query);
    setInputVal('');
  };

  const handleQuickChip = (chipText: string) => {
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    onSendMessage?.(chipText);
  };

  const stopSpeaking = () => {
    if (onStopSpeaking) {
      onStopSpeaking();
      return;
    }
    stopAnySpeaking();
    setLocalSpeakingId(null);
    onAgentStatusChange('idle');
  };

  const handleSpeakToggle = (message: ConversationalMessage) => {
    if (effectiveSpeakingId === message.id) {
      stopSpeaking();
      return;
    }

    if (onSpeakMessage) {
      onSpeakMessage(message);
      return;
    }

    setLocalSpeakingId(message.id);
    const started = speakText(message.content, {
      accent: voicePreferences.accent,
      voiceURI: voicePreferences.voiceURI,
      rate: voicePreferences.rate,
      pitch: voicePreferences.pitch,
      onStatusChange: onAgentStatusChange,
      onFinish: () => setLocalSpeakingId(null),
    });
    if (!started) setLocalSpeakingId(null);
  };

  const toggleThinking = (messageId: string) => {
    setExpandedThinkingIds((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) next.delete(messageId);
      else next.add(messageId);
      return next;
    });
  };

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={onToggleOpen}
        className="glass-obsidian fixed bottom-24 right-6 z-30 flex cursor-pointer items-center gap-2 rounded-2xl border border-[#00f0ff]/40 px-3.5 py-2 font-mono text-xs font-bold tracking-wider text-cyan-300 shadow-[0_0_20px_rgba(0,240,255,0.2)] transition-all hover:scale-105 hover:border-[#00f0ff]/80 hover:text-white"
      >
        <Terminal className="h-3.5 w-3.5 text-cyan-400" />
        <span>CHAT WITH NEXUS</span>
        {queuedCount > 0 && (
          <span className="rounded-full border border-amber-300/50 bg-amber-500/15 px-1.5 py-0.5 text-[8px] font-black text-amber-100">
            {queuedCount} QUEUED
          </span>
        )}
        <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
      </button>
    );
  }

  return (
    <div
      className={`glass-obsidian fixed bottom-24 right-6 z-30 isolate flex animate-fade-in flex-col overflow-hidden rounded-2xl border border-[#00f0ff]/40 font-mono shadow-[0_16px_40px_rgba(0,0,0,0.85),0_0_25px_rgba(0,240,255,0.2)] transition-all duration-300 select-none ${
        isExpanded
          ? 'h-[640px] max-h-[85vh] w-[680px] max-w-[94vw]'
          : 'h-[500px] max-h-[75vh] w-96 max-w-[94vw] md:w-[440px]'
      }`}
    >
      {/* ── Header: identity, history, voice, model ─────────────────────── */}
      <div className="shrink-0 border-b border-[#00f0ff]/20 bg-[#060a16]/95 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-cyan-400/40 bg-cyan-950/80">
              <Terminal className="h-3.5 w-3.5 text-cyan-400" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-[11px] font-black uppercase tracking-[0.22em] text-cyan-100">
                NEXUS Chat
              </div>
              <div className="truncate text-[7.5px] font-bold uppercase tracking-[0.18em] text-slate-500">
                Conversational Cortex
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <HistoryDrawer
              sessions={sessions}
              source={historySource}
              currentSessionId={currentSessionId}
              isLoading={isHistoryLoading}
              disabled={isBusy}
              onRefresh={onRefreshHistory}
              onNewChat={onNewChat}
              onOpenSession={onOpenSession}
              onRenameSession={onRenameSession}
              onDeleteSession={onDeleteSession}
              onClearAll={onClearHistory}
            />

            <VoiceSettings
              preferences={voicePreferences}
              onChange={onVoicePreferencesChange}
              voiceEnabled={capabilities.voiceReplies}
              onVoiceEnabledChange={(enabled) =>
                onCapabilitiesChange({ ...capabilities, voiceReplies: enabled })
              }
              agentStatus={agentStatus}
              onStatusChange={onAgentStatusChange}
              align="right"
              placement="bottom"
            />

            <button
              type="button"
              onClick={() => setIsExpanded((prev) => !prev)}
              title={isExpanded ? 'Collapse view' : 'Expand view'}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/70 text-slate-400 transition-colors hover:border-cyan-400/50 hover:text-white cursor-pointer"
            >
              {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>

            <button
              type="button"
              onClick={onToggleOpen}
              title="Minimize chat"
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/70 text-slate-400 transition-colors hover:border-cyan-400/50 hover:text-white cursor-pointer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="mt-2.5 flex items-center gap-2">
          <ModelPicker
            catalog={modelCatalog}
            value={selectedModelId}
            onChange={onModelChange}
            disabled={isBusy}
            align="left"
            className="min-w-0"
          />
          <button
            type="button"
            onClick={() => void onNewChat()}
            disabled={isBusy}
            title="Start a new chat"
            className="flex shrink-0 items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-950/70 px-2.5 py-2 text-[9px] font-black uppercase tracking-wider text-slate-300 transition-colors hover:border-cyan-400/50 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5" />
            New
          </button>
          <div className="ml-auto hidden min-w-0 truncate text-right text-[7.5px] font-bold uppercase tracking-wider text-slate-600 sm:block">
            {historySource === 'backend' ? 'Server history' : 'Browser history'}
          </div>
        </div>
      </div>

      {/* ── Quick prompts ─────────────────────────────────────────────────── */}
      <div className="scrollbar-none flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-slate-800 bg-[#03060f]/80 px-3 py-1.5">
        <button type="button" onClick={() => handleQuickChip('hi')} className="shrink-0 rounded-md border border-cyan-400/30 bg-cyan-950/60 px-2 py-0.5 text-[9px] font-semibold text-cyan-300 transition-all hover:bg-cyan-900 hover:text-white cursor-pointer">
          👋 Greeting
        </button>
        <button type="button" onClick={() => handleQuickChip('what tools do you have?')} className="shrink-0 rounded-md border border-slate-800 bg-slate-900/80 px-2 py-0.5 text-[9px] text-slate-300 transition-all hover:border-cyan-400/40 hover:bg-cyan-950 hover:text-cyan-200 cursor-pointer">
          🛠️ List Tools
        </button>
        <button type="button" onClick={() => handleQuickChip('system health')} className="shrink-0 rounded-md border border-slate-800 bg-slate-900/80 px-2 py-0.5 text-[9px] text-slate-300 transition-all hover:border-cyan-400/40 hover:bg-cyan-950 hover:text-cyan-200 cursor-pointer">
          ⚡ System Health
        </button>
        <button type="button" onClick={() => handleQuickChip('open code compiler')} className="shrink-0 rounded-md border border-slate-800 bg-slate-900/80 px-2 py-0.5 text-[9px] text-emerald-400/80 transition-all hover:border-emerald-400/40 hover:bg-emerald-950 hover:text-emerald-300 cursor-pointer">
          &lt;/&gt; Code Sandbox
        </button>
      </div>

      {/* ── Message feed ──────────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        onScroll={handleMessageScroll}
        className="min-h-0 flex-1 space-y-3.5 overflow-y-auto p-3.5 text-xs"
      >
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isCopied = copiedId === msg.id;
          const segments = parseContentSegments(msg.content || '');
          const hasCode = segments.some((segment) => segment.type === 'code');
          const thinking = !isUser && capabilities.extendedThinking
            ? cleanThinkingText(msg.thinking, msg.content)
            : '';
          const thinkingExpanded = expandedThinkingIds.has(msg.id);
          const messageModelName = !isUser ? modelDisplayName(msg.model, modelCatalog) : null;
          const isSpeakingThis = effectiveSpeakingId === msg.id;

          return (
            <div key={msg.id} className={`group flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
              <div className="mb-1 flex max-w-full flex-wrap items-center gap-1.5 text-[8.5px] text-slate-400">
                {isUser ? (
                  <>
                    <span>{msg.timestamp}</span>
                    <span className="font-bold uppercase tracking-wider text-cyan-400">Operator</span>
                  </>
                ) : (
                  <>
                    <span className="flex items-center gap-1 font-bold uppercase tracking-wider text-cyan-300">
                      <Sparkles className="h-2.5 w-2.5 text-cyan-400" />
                      NEXUS AI
                    </span>
                    <span>{msg.timestamp}</span>
                    {messageModelName && (
                      <span
                        title={msg.model}
                        className="flex max-w-44 items-center gap-1 rounded border border-cyan-400/25 bg-cyan-950/70 px-1.5 py-0.5 font-bold text-cyan-200"
                      >
                        <Cpu className="h-2.5 w-2.5 shrink-0" />
                        <span className="truncate">{messageModelName}</span>
                      </span>
                    )}
                    {msg.difficulty && (
                      <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-semibold text-slate-400">
                        {msg.difficulty.toUpperCase()}
                      </span>
                    )}
                    {msg.status === 'stopped' && (
                      <span className="rounded border border-amber-300/50 bg-amber-500/15 px-1.5 py-0.5 font-black text-amber-100">
                        STOPPED
                      </span>
                    )}
                    {msg.status === 'error' && (
                      <span className="rounded border border-red-300/50 bg-red-500/15 px-1.5 py-0.5 font-black text-red-100">
                        STREAM ERROR
                      </span>
                    )}
                  </>
                )}
              </div>

              <div className={hasCode ? 'w-[97%] max-w-full' : 'max-w-[92%]'}>
                <div
                  className={`rounded-2xl border p-3 text-[11px] leading-relaxed transition-all ${
                    isUser
                      ? 'rounded-br-xs border-cyan-400/50 bg-cyan-950/70 text-white shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                      : 'rounded-bl-xs border-[#00f0ff]/25 bg-[#040814]/90 text-slate-200 shadow-inner'
                  }`}
                >
                  {!isUser && msg.toolsUsed && msg.toolsUsed.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1 border-b border-slate-800 pb-1.5">
                      {msg.toolsUsed.map((tool, idx) => (
                        <span
                          key={`${tool}-${idx}`}
                          className="flex items-center gap-1 rounded border border-cyan-400/30 bg-cyan-950/80 px-1.5 py-0.5 text-[8px] font-bold text-cyan-300"
                        >
                          <Zap className="h-2 w-2 text-cyan-400" />
                          <span>{tool.startsWith('MCP:') ? tool : `TOOL: ${tool}`}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {thinking && (
                    <div className="mb-2.5 overflow-hidden rounded-xl border border-violet-400/25 bg-violet-950/25">
                      <button
                        type="button"
                        onClick={() => toggleThinking(msg.id)}
                        aria-expanded={thinkingExpanded}
                        className="flex w-full items-center gap-1.5 px-2.5 py-2 text-left text-[8.5px] font-black uppercase tracking-[0.18em] text-violet-200 transition-colors hover:bg-violet-500/10 cursor-pointer"
                      >
                        <Brain className="h-3 w-3 text-violet-300" />
                        <span className="flex-1">Thinking</span>
                        <ChevronRight className={`h-3 w-3 transition-transform ${thinkingExpanded ? 'rotate-90' : ''}`} />
                      </button>
                      {thinkingExpanded && (
                        <div className="max-h-44 overflow-y-auto whitespace-pre-wrap border-t border-violet-400/15 px-3 py-2 font-sans text-[10px] leading-relaxed text-violet-100/75">
                          {thinking}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="font-sans text-[11.5px] leading-relaxed">
                    {segments.length > 0 ? (
                      segments.map((segment, segmentIndex) => {
                        const segmentKey = `${msg.id}-segment-${segmentIndex}`;
                        if (segment.type === 'code') {
                          const artifactId = `${msg.id}-artifact-${segmentIndex}`;
                          return capabilities.artifacts && !isUser ? (
                            <ArtifactCard
                              key={segmentKey}
                              artifactId={artifactId}
                              language={segment.language}
                              code={segment.code}
                              copiedId={copiedId}
                              onCopy={(id, text) => void handleCopy(id, text)}
                              onDownload={handleDownloadArtifact}
                            />
                          ) : (
                            <pre
                              key={segmentKey}
                              className="my-2 max-h-64 overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-3 font-mono text-[10px] leading-relaxed text-slate-100"
                            >
                              <code>{segment.code}</code>
                            </pre>
                          );
                        }
                        return (
                          <div key={segmentKey}>
                            {renderFormattedText(segment.text.trim(), segmentKey)}
                          </div>
                        );
                      })
                    ) : (
                      <span className="text-slate-500">…</span>
                    )}
                  </div>

                  {!isUser && msg.actionTriggers && msg.actionTriggers.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-slate-800/80 pt-2">
                      {msg.actionTriggers.map((act, idx) => (
                        <button
                          key={`${act.action}-${idx}`}
                          type="button"
                          onClick={() => onTriggerAction?.(act.action, act.payload)}
                          className="flex items-center gap-1 rounded-lg border border-cyan-400/50 bg-cyan-950/90 px-2 py-1 text-[9px] font-bold text-cyan-200 shadow-sm transition-all hover:border-cyan-300 hover:bg-cyan-900 cursor-pointer"
                        >
                          {act.action === 'OPEN_MULTIMODAL' && <Eye className="h-2.5 w-2.5 text-cyan-400" />}
                          {act.action === 'OPEN_CODE' && <Code2 className="h-2.5 w-2.5 text-emerald-400" />}
                          {act.action === 'OPEN_CANVAS' && <Layers className="h-2.5 w-2.5 text-purple-400" />}
                          {act.action === 'OPEN_VIDEO' && <Film className="h-2.5 w-2.5 text-amber-400" />}
                          <span>{act.label}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className={`mt-1.5 flex items-center gap-1 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <button
                    type="button"
                    onClick={() => void handleCopy(msg.id, msg.content)}
                    title="Copy message"
                    className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/80 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-slate-400 transition-colors hover:border-cyan-400/40 hover:text-cyan-100 cursor-pointer"
                  >
                    {isCopied ? <Check className="h-3 w-3 text-emerald-300" /> : <Copy className="h-3 w-3" />}
                    {isCopied ? 'Copied' : 'Copy'}
                  </button>

                  {!isUser && (
                    <button
                      type="button"
                      onClick={() => handleSpeakToggle(msg)}
                      disabled={!msg.content.trim() || isBusy}
                      title={isSpeakingThis ? 'Stop speaking' : 'Listen to this reply'}
                      className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[8px] font-black uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer ${
                        isSpeakingThis
                          ? 'border-amber-300/60 bg-amber-500/15 text-amber-100'
                          : 'border-slate-800 bg-slate-950/80 text-slate-400 hover:border-cyan-400/40 hover:text-cyan-100'
                      }`}
                    >
                      {isSpeakingThis ? <Square className="h-3 w-3" /> : <Volume2 className="h-3 w-3" />}
                      {isSpeakingThis ? 'Stop' : 'Listen'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {(isGenerating || queuedCount > 0) && (
          <div
            aria-live="polite"
            className="flex items-center gap-2 rounded-xl border border-cyan-500/40 bg-cyan-950/60 p-2.5 text-[10.5px] text-cyan-200 shadow-[0_0_12px_rgba(0,240,255,0.2)]"
          >
            <Zap className={`h-3.5 w-3.5 shrink-0 text-cyan-400 ${isGenerating ? 'animate-spin' : ''}`} />
            <span className="min-w-0 flex-1">
              {isGenerating ? 'NEXUS is working…' : 'NEXUS will continue shortly…'}
              {queuedCount > 0 ? ` ${queuedCount} queued.` : ''}
            </span>
            {isGenerating && onStopGeneration && (
              <button
                type="button"
                onClick={onStopGeneration}
                title="Stop generating"
                className="flex shrink-0 items-center gap-1 rounded-lg border border-red-300/50 bg-red-500/15 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-red-100 transition-colors hover:bg-red-500/25 cursor-pointer"
              >
                <Square className="h-3 w-3" />
                Stop
              </button>
            )}
          </div>
        )}
      </div>

      {!isNearBottom && (
        <button
          type="button"
          onClick={() => scrollToLatest()}
          className="absolute bottom-[68px] right-3 z-20 flex items-center gap-1 rounded-full border border-cyan-300/50 bg-slate-950/95 px-2.5 py-1.5 text-[8px] font-black uppercase tracking-wider text-cyan-100 shadow-[0_8px_24px_rgba(0,0,0,0.45)] transition-all hover:-translate-y-0.5 cursor-pointer"
        >
          Jump to latest
          <ChevronDown className="h-3 w-3" />
        </button>
      )}

      {/* ── Composer: capabilities, input, stop/send ─────────────────────── */}
      <form
        onSubmit={handleSend}
        className="flex shrink-0 items-center gap-1.5 border-t border-[#00f0ff]/20 bg-[#040713]/95 p-2.5"
      >
        <CapabilitiesPanel
          capabilities={capabilities}
          onChange={onCapabilitiesChange}
          selectedModel={selectedModel}
          capabilityLabels={modelCatalog.capability_labels}
          align="left"
          placement="top"
        />

        <input
          ref={inputRef}
          type="text"
          value={inputVal}
          onChange={(event) => setInputVal(event.target.value)}
          onKeyDown={(event) => {
            const nativeEvent = event.nativeEvent as KeyboardEvent;
            if (event.key === 'Enter' && (nativeEvent.isComposing || nativeEvent.keyCode === 229)) {
              event.preventDefault();
            }
          }}
          placeholder={isGenerating ? 'Nexus is working — type to queue…' : 'Ask NEXUS or dispatch command...'}
          aria-label="Message NEXUS"
          className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-slate-950/90 px-3 py-2 font-mono text-xs text-white outline-none transition-colors placeholder:text-slate-500 focus:border-cyan-400/60"
        />

        {isGenerating && onStopGeneration && (
          <button
            type="button"
            onClick={onStopGeneration}
            title="Stop generating"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-red-300/60 bg-red-500/15 text-red-100 transition-colors hover:bg-red-500/25 cursor-pointer"
          >
            <Square className="h-3.5 w-3.5" />
          </button>
        )}

        {agentStatus === 'speaking' && (
          <button
            type="button"
            onClick={stopSpeaking}
            title="Stop voice output"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-amber-300/60 bg-amber-500/15 text-amber-100 transition-colors hover:bg-amber-500/25 cursor-pointer"
          >
            <Square className="h-3.5 w-3.5" />
          </button>
        )}

        <button
          type="submit"
          disabled={!inputVal.trim()}
          title={isGenerating ? 'Queue message' : 'Send message'}
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-bold transition-all ${
            inputVal.trim()
              ? 'cursor-pointer bg-cyan-500 text-black shadow-[0_0_10px_rgba(0,240,255,0.3)] hover:bg-cyan-400 active:scale-95'
              : 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-600'
          }`}
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  );
};
