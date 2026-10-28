import React, { useEffect, useMemo, useState } from 'react';
import {
  Check,
  Clock,
  Cloud,
  HardDrive,
  History,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import {
  formatSessionUpdatedAt,
  groupChatSessions,
  type HistorySource,
} from '../utils/chatHistory';
import type { ChatSessionSummary } from '../types';

type MaybePromise<T> = T | Promise<T>;

interface HistoryDrawerProps {
  sessions: ChatSessionSummary[];
  source: HistorySource;
  currentSessionId: string | null;
  isLoading?: boolean;
  disabled?: boolean;
  onRefresh: () => MaybePromise<void>;
  onNewChat: () => MaybePromise<boolean | void>;
  onOpenSession: (sessionId: string) => MaybePromise<boolean | void>;
  onRenameSession: (sessionId: string, title: string) => MaybePromise<boolean | void>;
  onDeleteSession: (sessionId: string) => MaybePromise<boolean | void>;
  onClearAll?: () => MaybePromise<boolean | void>;
  className?: string;
}

function shortModelName(model: string | null): string | null {
  if (!model) return null;
  if (model === 'auto') return 'NEXUS Auto';
  return model.split('/').filter(Boolean).pop() || model;
}

export const HistoryDrawer: React.FC<HistoryDrawerProps> = ({
  sessions,
  source,
  currentSessionId,
  isLoading = false,
  disabled = false,
  onRefresh,
  onNewChat,
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onClearAll,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmClearAll, setConfirmClearAll] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const filteredSessions = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter((session) =>
      [session.title, session.preview, session.model || '', session.id]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [searchQuery, sessions]);

  const groupedSessions = useMemo(
    () => groupChatSessions(filteredSessions),
    [filteredSessions],
  );

  useEffect(() => {
    if (!isOpen) return undefined;
    void onRefresh();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        setEditingId(null);
        setConfirmDeleteId(null);
        setConfirmClearAll(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onRefresh]);

  const closeDrawer = () => {
    setIsOpen(false);
    setEditingId(null);
    setConfirmDeleteId(null);
    setConfirmClearAll(false);
  };

  const handleNewChat = async () => {
    if (disabled || isCreating) return;
    setIsCreating(true);
    try {
      const result = await onNewChat();
      if (result !== false) closeDrawer();
    } finally {
      setIsCreating(false);
    }
  };

  const handleOpenSession = async (sessionId: string) => {
    if (disabled || openingId) return;
    if (sessionId === currentSessionId) {
      closeDrawer();
      return;
    }
    setOpeningId(sessionId);
    try {
      const result = await onOpenSession(sessionId);
      if (result !== false) closeDrawer();
    } finally {
      setOpeningId(null);
    }
  };

  const startRename = (session: ChatSessionSummary) => {
    setEditingId(session.id);
    setDraftTitle(session.title);
    setConfirmDeleteId(null);
  };

  const saveRename = async (sessionId: string) => {
    const title = draftTitle.trim();
    if (!title || busyId) return;
    setBusyId(sessionId);
    try {
      const result = await onRenameSession(sessionId, title);
      if (result !== false) setEditingId(null);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (sessionId: string) => {
    if (busyId) return;
    setBusyId(sessionId);
    try {
      const result = await onDeleteSession(sessionId);
      if (result !== false) {
        setConfirmDeleteId(null);
        if (editingId === sessionId) setEditingId(null);
      }
    } finally {
      setBusyId(null);
    }
  };

  const handleClearAll = async () => {
    if (!onClearAll || busyId) return;
    setBusyId('clear-all');
    try {
      const result = await onClearAll();
      if (result !== false) {
        setConfirmClearAll(false);
        setSearchQuery('');
        setEditingId(null);
        setConfirmDeleteId(null);
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title="Chat history"
        className={`relative flex h-8 w-8 items-center justify-center rounded-xl border font-mono transition-all cursor-pointer ${
          isOpen
            ? 'border-cyan-300/70 bg-cyan-500/15 text-cyan-100 shadow-[0_0_14px_rgba(0,240,255,0.18)]'
            : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-cyan-400/50 hover:text-cyan-200'
        } ${className}`}
      >
        <History className="h-3.5 w-3.5" />
        {sessions.length > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-cyan-400 px-0.5 text-[7px] font-black text-slate-950">
            {sessions.length > 99 ? '99' : sessions.length}
          </span>
        )}
        <span className="sr-only">Open chat history</span>
      </button>

      {isOpen && (
        <div className="absolute inset-0 z-40 flex animate-fade-in">
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Chat history"
            className="flex h-full w-[88%] max-w-[330px] shrink-0 flex-col border-r border-cyan-400/25 bg-[#050914]/99 font-mono shadow-[24px_0_60px_rgba(0,0,0,0.55)] backdrop-blur-2xl"
          >
            <div className="border-b border-slate-800 px-3.5 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-200">
                    <History className="h-3.5 w-3.5 text-cyan-400" />
                    History
                  </div>
                  <p className="mt-1 text-[9px] leading-relaxed text-slate-500">
                    Reopen, rename, or delete past conversations.
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void onRefresh()}
                    disabled={isLoading}
                    title="Refresh history"
                    className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                  </button>
                  <button
                    type="button"
                    onClick={closeDrawer}
                    title="Close history"
                    className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white cursor-pointer"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handleNewChat()}
                disabled={disabled || isCreating}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-300/70 bg-cyan-400 px-3 py-2.5 text-[10px] font-black uppercase tracking-[0.18em] text-slate-950 shadow-[0_0_18px_rgba(0,240,255,0.22)] transition-all hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
              >
                {isCreating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                New chat
              </button>

              <div className="relative mt-2.5">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search conversations..."
                  aria-label="Search conversations"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950/90 py-2 pl-9 pr-8 text-[10px] font-bold text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/70"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    title="Clear search"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-500 hover:text-white cursor-pointer"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>

              <div
                className={`mt-2.5 flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[8px] font-bold uppercase tracking-wider ${
                  source === 'backend'
                    ? 'border-emerald-400/25 bg-emerald-950/35 text-emerald-200'
                    : 'border-amber-400/25 bg-amber-950/30 text-amber-100'
                }`}
              >
                {source === 'backend' ? <Cloud className="h-3 w-3" /> : <HardDrive className="h-3 w-3" />}
                {source === 'backend' ? 'Synced to NEXUS server' : 'Stored in this browser only'}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {isLoading && sessions.length === 0 ? (
                <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 text-center text-slate-500">
                  <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
                  <span className="text-[9px] font-bold uppercase tracking-[0.18em]">Loading history</span>
                </div>
              ) : filteredSessions.length === 0 ? (
                <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 px-5 text-center">
                  <MessageSquare className="h-6 w-6 text-slate-700" />
                  <div className="text-[10px] font-black text-slate-300">
                    {searchQuery ? 'No matching conversations' : 'No conversations yet'}
                  </div>
                  <p className="text-[9px] leading-relaxed text-slate-500">
                    {searchQuery
                      ? 'Try a different title, message preview, or model name.'
                      : 'Your first completed conversation will appear here automatically.'}
                  </p>
                </div>
              ) : (
                groupedSessions.map((group) => (
                  <div key={group.label} className="mb-3 last:mb-1">
                    <div className="px-2 pb-1.5 pt-2 text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                      {group.label}
                    </div>
                    <div className="space-y-1">
                      {group.sessions.map((session) => {
                        const isCurrent = session.id === currentSessionId;
                        const isEditing = editingId === session.id;
                        const isConfirmingDelete = confirmDeleteId === session.id;
                        const isBusy = busyId === session.id;
                        const modelName = shortModelName(session.model);

                        return (
                          <div
                            key={session.id}
                            className={`group rounded-xl border transition-all ${
                              isCurrent
                                ? 'border-cyan-400/55 bg-cyan-500/10 shadow-[inset_0_0_18px_rgba(0,240,255,0.05)]'
                                : 'border-transparent hover:border-slate-700 hover:bg-slate-900/80'
                            }`}
                          >
                            {isEditing ? (
                              <div className="flex items-center gap-1.5 px-2 py-2">
                                <input
                                  autoFocus
                                  value={draftTitle}
                                  onChange={(event) => setDraftTitle(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Enter') void saveRename(session.id);
                                    if (event.key === 'Escape') setEditingId(null);
                                  }}
                                  maxLength={80}
                                  aria-label="Conversation title"
                                  className="min-w-0 flex-1 rounded-lg border border-cyan-400/50 bg-slate-950 px-2 py-1.5 text-[10px] font-bold text-white outline-none"
                                />
                                <button
                                  type="button"
                                  onClick={() => void saveRename(session.id)}
                                  disabled={!draftTitle.trim() || isBusy}
                                  title="Save title"
                                  className="rounded-lg bg-cyan-400 p-1.5 text-slate-950 disabled:opacity-50 cursor-pointer"
                                >
                                  {isBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setEditingId(null)}
                                  title="Cancel rename"
                                  className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:text-white cursor-pointer"
                                >
                                  <X className="h-3 w-3" />
                                </button>
                              </div>
                            ) : isConfirmingDelete ? (
                              <div className="px-3 py-2.5">
                                <div className="text-[9px] font-black text-red-200">Delete this conversation?</div>
                                <p className="mt-1 line-clamp-1 text-[8.5px] text-slate-500">{session.title}</p>
                                <div className="mt-2 flex gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => void handleDelete(session.id)}
                                    disabled={isBusy}
                                    className="flex-1 rounded-lg bg-red-500 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-white disabled:opacity-50 cursor-pointer"
                                  >
                                    {isBusy ? 'Deleting...' : 'Delete'}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setConfirmDeleteId(null)}
                                    className="flex-1 rounded-lg border border-slate-700 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-slate-300 cursor-pointer"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="flex items-stretch gap-1 px-1.5 py-1.5">
                                <button
                                  type="button"
                                  onClick={() => void handleOpenSession(session.id)}
                                  disabled={disabled || Boolean(openingId)}
                                  title={isCurrent ? 'Current conversation' : 'Open conversation'}
                                  className="min-w-0 flex-1 rounded-lg px-1.5 py-1 text-left disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
                                >
                                  <div className="flex items-center gap-1.5">
                                    <span className={`min-w-0 flex-1 truncate text-[10px] font-black ${isCurrent ? 'text-cyan-50' : 'text-slate-100'}`}>
                                      {session.title || 'New conversation'}
                                    </span>
                                    {openingId === session.id ? (
                                      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-cyan-300" />
                                    ) : isCurrent ? (
                                      <span className="shrink-0 rounded bg-cyan-400 px-1.5 py-0.5 text-[7px] font-black uppercase tracking-wider text-slate-950">
                                        Current
                                      </span>
                                    ) : null}
                                  </div>
                                  {session.preview && (
                                    <p className="mt-1 line-clamp-2 text-[8.5px] leading-relaxed text-slate-500">
                                      {session.preview}
                                    </p>
                                  )}
                                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[7.5px] font-bold uppercase tracking-wider text-slate-600">
                                    <span className="flex items-center gap-1">
                                      <Clock className="h-2.5 w-2.5" />
                                      {formatSessionUpdatedAt(session.updated_at)}
                                    </span>
                                    <span>{session.message_count} msg</span>
                                    {modelName && (
                                      <span className="max-w-28 truncate text-cyan-300/70">{modelName}</span>
                                    )}
                                  </div>
                                </button>

                                <div className="flex shrink-0 flex-col justify-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                                  <button
                                    type="button"
                                    onClick={() => startRename(session)}
                                    disabled={disabled || isBusy}
                                    title="Rename conversation"
                                    className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-cyan-200 disabled:opacity-50 cursor-pointer"
                                  >
                                    <Pencil className="h-3 w-3" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setConfirmDeleteId(session.id)}
                                    disabled={disabled || isBusy}
                                    title="Delete conversation"
                                    className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-red-950/70 hover:text-red-300 disabled:opacity-50 cursor-pointer"
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="border-t border-slate-800 bg-slate-950/70 px-3.5 py-2.5">
              {onClearAll && sessions.length > 0 ? (
                confirmClearAll ? (
                  <div>
                    <div className="text-[8.5px] font-black text-red-200">Clear all chat history?</div>
                    <div className="mt-2 flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => void handleClearAll()}
                        disabled={busyId === 'clear-all'}
                        className="flex-1 rounded-lg bg-red-500 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-white disabled:opacity-50 cursor-pointer"
                      >
                        {busyId === 'clear-all' ? 'Clearing...' : 'Clear all'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmClearAll(false)}
                        className="flex-1 rounded-lg border border-slate-700 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-slate-300 cursor-pointer"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmClearAll(true)}
                    disabled={disabled}
                    className="text-[8px] font-black uppercase tracking-wider text-slate-500 transition-colors hover:text-red-300 disabled:opacity-50 cursor-pointer"
                  >
                    Clear all history
                  </button>
                )
              ) : (
                <p className="text-[8px] leading-relaxed text-slate-600">
                  New conversations save after the first completed reply.
                </p>
              )}
            </div>
          </aside>

          <button
            type="button"
            aria-label="Close chat history"
            onClick={closeDrawer}
            className="min-w-0 flex-1 cursor-default bg-black/45"
          />
        </div>
      )}
    </>
  );
};
