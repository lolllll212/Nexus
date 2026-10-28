import { nexusJson } from '../api';
import type {
  ChatSessionRecord,
  ChatSessionSummary,
  ConversationalMessage,
  StoredChatMessage,
} from '../types';

/**
 * Chat-history client for the Claude-style history window.
 *
 * The FastAPI history API is authoritative and identity-scoped. For static
 * previews or a temporarily unavailable backend, the same operations are
 * mirrored into localStorage and the caller receives `source: 'local'`, so
 * the UI can label the state honestly instead of pretending it synced.
 */

export type HistorySource = 'backend' | 'local';

export interface ChatSessionListResult {
  sessions: ChatSessionSummary[];
  source: HistorySource;
}

export interface ChatSessionResult {
  session: ChatSessionRecord | null;
  source: HistorySource;
}

export interface ChatHistoryDeleteResult {
  deleted: boolean;
  source: HistorySource;
}

export interface ChatHistoryClearResult {
  deleted: number;
  source: HistorySource;
}

export interface CreateChatSessionInput {
  id?: string;
  sessionId?: string;
  title?: string | null;
  model?: string | null;
  messages?: StoredChatMessage[];
}

export interface AppendChatMessagesOptions {
  model?: string | null;
  title?: string | null;
}

export const HISTORY_STORAGE_KEY = 'nexus_chat_sessions_v1';

const MAX_LOCAL_SESSIONS = 200;
const MAX_LOCAL_MESSAGES = 500;
const TITLE_MAX_CHARS = 80;

function nowIso(): string {
  return new Date().toISOString();
}

export function newSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function normalizeRole(value: unknown): StoredChatMessage['role'] {
  const role = typeof value === 'string' ? value.toLowerCase() : '';
  if (role === 'assistant' || role === 'nexus') return 'assistant';
  if (role === 'system') return 'system';
  return 'user';
}

function normalizeStoredMessage(raw: unknown): StoredChatMessage | null {
  if (!isRecord(raw)) return null;
  const toolsUsed = stringArray(raw.tools_used ?? raw.toolsUsed);
  const model = nullableString(raw.model);
  const message: StoredChatMessage = {
    id: stringValue(raw.id, `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`),
    role: normalizeRole(raw.role),
    content: stringValue(raw.content),
    timestamp: stringValue(raw.timestamp, nowIso()),
  };
  if (model) message.model = model;
  if (toolsUsed.length > 0) message.tools_used = toolsUsed;
  return message;
}

function normalizeStoredMessages(raw: unknown): StoredChatMessage[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const messages: StoredChatMessage[] = [];
  for (const item of raw) {
    const message = normalizeStoredMessage(item);
    if (!message || seen.has(message.id)) continue;
    seen.add(message.id);
    messages.push(message);
  }
  return messages.slice(-MAX_LOCAL_MESSAGES);
}

export function deriveSessionTitle(messages: StoredChatMessage[]): string {
  const firstUserMessage = messages.find(
    (message) => message.role === 'user' && message.content.trim(),
  );
  if (!firstUserMessage) return 'New conversation';
  const text = firstUserMessage.content.replace(/\s+/g, ' ').trim();
  return text.length > TITLE_MAX_CHARS
    ? `${text.slice(0, TITLE_MAX_CHARS).trimEnd()}…`
    : text;
}

function previewFromMessages(messages: StoredChatMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const content = messages[index].content.replace(/\s+/g, ' ').trim();
    if (content) return content.slice(0, 140);
  }
  return '';
}

export function normalizeSessionRecord(raw: unknown): ChatSessionRecord | null {
  const candidate = isRecord(raw) && isRecord(raw.session) ? raw.session : raw;
  if (!isRecord(candidate) || typeof candidate.id !== 'string' || !candidate.id.trim()) {
    return null;
  }

  const messages = normalizeStoredMessages(candidate.messages);
  const fallbackTime = nowIso();
  return {
    id: candidate.id,
    title: stringValue(candidate.title, deriveSessionTitle(messages)).slice(0, TITLE_MAX_CHARS),
    model: nullableString(candidate.model),
    created_at: stringValue(candidate.created_at, fallbackTime),
    updated_at: stringValue(candidate.updated_at, stringValue(candidate.created_at, fallbackTime)),
    messages,
  };
}

export function summaryFromRecord(record: ChatSessionRecord): ChatSessionSummary {
  return {
    id: record.id,
    title: record.title || deriveSessionTitle(record.messages),
    model: record.model,
    created_at: record.created_at,
    updated_at: record.updated_at,
    message_count: record.messages.length,
    preview: previewFromMessages(record.messages),
  };
}

function normalizeSessionSummary(raw: unknown): ChatSessionSummary | null {
  if (!isRecord(raw) || typeof raw.id !== 'string' || !raw.id.trim()) return null;
  const record = normalizeSessionRecord(raw);
  if (record && Array.isArray(raw.messages)) return summaryFromRecord(record);

  const fallbackTime = nowIso();
  const messageCount =
    typeof raw.message_count === 'number' && Number.isFinite(raw.message_count)
      ? Math.max(0, Math.trunc(raw.message_count))
      : 0;
  return {
    id: raw.id,
    title: stringValue(raw.title, 'New conversation'),
    model: nullableString(raw.model),
    created_at: stringValue(raw.created_at, fallbackTime),
    updated_at: stringValue(raw.updated_at, stringValue(raw.created_at, fallbackTime)),
    message_count: messageCount,
    preview: stringValue(raw.preview),
  };
}

function sortSessionSummaries(sessions: ChatSessionSummary[]): ChatSessionSummary[] {
  return [...sessions].sort((a, b) => {
    const updated = Date.parse(b.updated_at) - Date.parse(a.updated_at);
    return Number.isFinite(updated) && updated !== 0
      ? updated
      : b.updated_at.localeCompare(a.updated_at);
  });
}

function sortSessionRecords(sessions: ChatSessionRecord[]): ChatSessionRecord[] {
  return [...sessions].sort((a, b) => {
    const updated = Date.parse(b.updated_at) - Date.parse(a.updated_at);
    return Number.isFinite(updated) && updated !== 0
      ? updated
      : b.updated_at.localeCompare(a.updated_at);
  });
}

// ── local fallback store ───────────────────────────────────────────────────

function readLocalSessions(): Record<string, ChatSessionRecord> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    const rawSessions: unknown[] = Array.isArray(parsed)
      ? parsed
      : isRecord(parsed) && Array.isArray(parsed.sessions)
        ? parsed.sessions
        : isRecord(parsed) && isRecord(parsed.sessions)
          ? Object.values(parsed.sessions)
          : isRecord(parsed)
            ? Object.values(parsed)
            : [];

    const sessions: Record<string, ChatSessionRecord> = {};
    for (const item of rawSessions) {
      const session = normalizeSessionRecord(item);
      if (session) sessions[session.id] = session;
    }
    return sessions;
  } catch {
    return {};
  }
}

function writeLocalSessions(sessions: Record<string, ChatSessionRecord>): void {
  if (typeof window === 'undefined') return;
  try {
    const pruned = sortSessionRecords(Object.values(sessions)).slice(0, MAX_LOCAL_SESSIONS);
    const next: Record<string, ChatSessionRecord> = {};
    for (const session of pruned) next[session.id] = session;
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Browser storage can be full/blocked; backend remains authoritative.
  }
}

export function cacheChatSession(session: ChatSessionRecord): ChatSessionRecord {
  const sessions = readLocalSessions();
  sessions[session.id] = session;
  writeLocalSessions(sessions);
  return session;
}

function createLocalSession(input: CreateChatSessionInput): ChatSessionRecord {
  const sessionId = input.id || input.sessionId || newSessionId();
  const sessions = readLocalSessions();
  const existing = sessions[sessionId];
  if (existing) return existing;

  const messages = normalizeStoredMessages(input.messages || []);
  const timestamp = nowIso();
  const session: ChatSessionRecord = {
    id: sessionId,
    title: (input.title?.trim() || deriveSessionTitle(messages)).slice(0, TITLE_MAX_CHARS),
    model: input.model ?? null,
    created_at: timestamp,
    updated_at: timestamp,
    messages,
  };
  sessions[session.id] = session;
  writeLocalSessions(sessions);
  return session;
}

function listLocalSessions(query = '', limit = 50): ChatSessionSummary[] {
  const needle = query.trim().toLowerCase();
  const sessions = sortSessionRecords(Object.values(readLocalSessions()));
  const filtered = needle
    ? sessions.filter(
        (session) =>
          session.title.toLowerCase().includes(needle) ||
          (session.model || '').toLowerCase().includes(needle) ||
          session.messages.some((message) => message.content.toLowerCase().includes(needle)),
      )
    : sessions;
  return filtered.slice(0, Math.max(1, Math.min(limit, 200))).map(summaryFromRecord);
}

function appendLocalMessages(
  sessionId: string,
  messages: StoredChatMessage[],
  options: AppendChatMessagesOptions = {},
): ChatSessionRecord {
  const sessions = readLocalSessions();
  const normalized = normalizeStoredMessages(messages);
  let session = sessions[sessionId];

  if (!session) {
    const timestamp = nowIso();
    session = {
      id: sessionId,
      title: (options.title?.trim() || deriveSessionTitle(normalized)).slice(0, TITLE_MAX_CHARS),
      model: options.model ?? null,
      created_at: timestamp,
      updated_at: timestamp,
      messages: [],
    };
    sessions[sessionId] = session;
  }

  const seen = new Set(session.messages.map((message) => message.id));
  for (const message of normalized) {
    if (!seen.has(message.id)) {
      session.messages.push(message);
      seen.add(message.id);
    }
  }
  session.messages = session.messages.slice(-MAX_LOCAL_MESSAGES);
  if (options.model) session.model = options.model;
  if (options.title?.trim()) session.title = options.title.trim().slice(0, TITLE_MAX_CHARS);
  else if (!session.title || session.title === 'New conversation') {
    session.title = deriveSessionTitle(session.messages);
  }
  session.updated_at = nowIso();
  sessions[sessionId] = session;
  writeLocalSessions(sessions);
  return session;
}

// ── public backend-first API ───────────────────────────────────────────────

export async function listChatSessions(
  query = '',
  limit = 50,
): Promise<ChatSessionListResult> {
  const params = new URLSearchParams();
  if (query.trim()) params.set('q', query.trim());
  params.set('limit', String(Math.max(1, Math.min(limit, 200))));

  try {
    const raw = await nexusJson<{ sessions?: unknown }>(
      `/api/history/sessions?${params.toString()}`,
    );
    const sessions = Array.isArray(raw.sessions)
      ? raw.sessions
          .map(normalizeSessionSummary)
          .filter((session): session is ChatSessionSummary => session !== null)
      : [];
    return { sessions: sortSessionSummaries(sessions), source: 'backend' };
  } catch {
    return { sessions: listLocalSessions(query, limit), source: 'local' };
  }
}

export async function getChatSession(sessionId: string): Promise<ChatSessionResult> {
  try {
    const raw = await nexusJson<unknown>(
      `/api/history/sessions/${encodeURIComponent(sessionId)}`,
    );
    const session = normalizeSessionRecord(raw);
    if (session) cacheChatSession(session);
    return { session, source: 'backend' };
  } catch {
    return { session: readLocalSessions()[sessionId] || null, source: 'local' };
  }
}

export async function createChatSession(
  input: CreateChatSessionInput = {},
): Promise<ChatSessionResult> {
  const sessionId = input.id || input.sessionId || newSessionId();
  const messages = normalizeStoredMessages(input.messages || []);
  try {
    const raw = await nexusJson<unknown>('/api/history/sessions', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        title: input.title ?? undefined,
        model: input.model ?? undefined,
        messages,
      }),
    });
    const session = normalizeSessionRecord(raw);
    if (session) {
      cacheChatSession(session);
      return { session, source: 'backend' };
    }
    throw new Error('History API returned an invalid session.');
  } catch {
    return {
      session: createLocalSession({ ...input, id: sessionId, messages }),
      source: 'local',
    };
  }
}

export async function appendChatMessages(
  sessionId: string,
  messages: StoredChatMessage[],
  options: AppendChatMessagesOptions = {},
): Promise<ChatSessionResult> {
  const normalized = normalizeStoredMessages(messages);
  try {
    const raw = await nexusJson<unknown>(
      `/api/history/sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: 'POST',
        body: JSON.stringify({
          messages: normalized,
          model: options.model ?? undefined,
          title: options.title ?? undefined,
        }),
      },
    );
    const session = normalizeSessionRecord(raw);
    if (session) {
      cacheChatSession(session);
      return { session, source: 'backend' };
    }
    throw new Error('History API returned an invalid session.');
  } catch {
    return {
      session: appendLocalMessages(sessionId, normalized, options),
      source: 'local',
    };
  }
}

export async function renameChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionResult> {
  const nextTitle = title.trim().slice(0, TITLE_MAX_CHARS);
  if (!nextTitle) return { session: readLocalSessions()[sessionId] || null, source: 'local' };

  try {
    const raw = await nexusJson<unknown>(
      `/api/history/sessions/${encodeURIComponent(sessionId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ title: nextTitle }),
      },
    );
    const session = normalizeSessionRecord(raw);
    if (session) {
      cacheChatSession(session);
      return { session, source: 'backend' };
    }
    throw new Error('History API returned an invalid session.');
  } catch {
    const sessions = readLocalSessions();
    const session = sessions[sessionId];
    if (!session) return { session: null, source: 'local' };
    session.title = nextTitle;
    session.updated_at = nowIso();
    sessions[sessionId] = session;
    writeLocalSessions(sessions);
    return { session, source: 'local' };
  }
}

export async function deleteChatSession(
  sessionId: string,
): Promise<ChatHistoryDeleteResult> {
  try {
    await nexusJson<unknown>(`/api/history/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
    const sessions = readLocalSessions();
    delete sessions[sessionId];
    writeLocalSessions(sessions);
    return { deleted: true, source: 'backend' };
  } catch {
    const sessions = readLocalSessions();
    const existed = Boolean(sessions[sessionId]);
    delete sessions[sessionId];
    writeLocalSessions(sessions);
    return { deleted: existed, source: 'local' };
  }
}

export async function clearChatSessions(): Promise<ChatHistoryClearResult> {
  try {
    const raw = await nexusJson<{ deleted?: unknown }>('/api/history/sessions', {
      method: 'DELETE',
    });
    writeLocalSessions({});
    return {
      deleted:
        typeof raw.deleted === 'number' && Number.isFinite(raw.deleted) ? raw.deleted : 0,
      source: 'backend',
    };
  } catch {
    const deleted = Object.keys(readLocalSessions()).length;
    writeLocalSessions({});
    return { deleted, source: 'local' };
  }
}

// ── UI/history conversions and formatting ──────────────────────────────────

function timestampForStorage(timestamp: string): string {
  // Existing UI messages sometimes carry a locale time-only string. Persist
  // true ISO values and replace display-only values with the sync time.
  if (/^\d{4}-\d{2}-\d{2}T/.test(timestamp)) return timestamp;
  return nowIso();
}

export function conversationalToStored(
  message: ConversationalMessage,
): StoredChatMessage {
  const stored: StoredChatMessage = {
    id: message.id,
    role: message.role,
    content: message.content,
    timestamp: timestampForStorage(message.timestamp),
  };
  if (message.model) stored.model = message.model;
  if (message.toolsUsed?.length) stored.tools_used = [...message.toolsUsed];
  return stored;
}

export function formatMessageTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return new Intl.DateTimeFormat(undefined, sameDay
    ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
    : {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
}

export function storedToConversational(
  message: StoredChatMessage,
): ConversationalMessage {
  const converted: ConversationalMessage = {
    id: message.id,
    role: normalizeRole(message.role),
    content: message.content,
    timestamp: formatMessageTimestamp(message.timestamp),
  };
  if (message.model) converted.model = message.model;
  if (message.tools_used?.length) converted.toolsUsed = [...message.tools_used];
  return converted;
}

export function getHistoryGroupLabel(updatedAt: string, reference = new Date()): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) return 'Older';

  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const dayDifference = Math.floor(
    (startOfDay(reference) - startOfDay(date)) / (24 * 60 * 60 * 1000),
  );

  if (dayDifference <= 0) return 'Today';
  if (dayDifference === 1) return 'Yesterday';
  if (dayDifference <= 7) return 'Previous 7 days';
  if (dayDifference <= 30) return 'Previous 30 days';
  return 'Older';
}

export interface ChatSessionGroup {
  label: string;
  sessions: ChatSessionSummary[];
}

const HISTORY_GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older'];

export function groupChatSessions(
  sessions: ChatSessionSummary[],
  reference = new Date(),
): ChatSessionGroup[] {
  const groups = new Map<string, ChatSessionSummary[]>();
  for (const session of sortSessionSummaries(sessions)) {
    const label = getHistoryGroupLabel(session.updated_at, reference);
    const existing = groups.get(label) || [];
    existing.push(session);
    groups.set(label, existing);
  }
  return HISTORY_GROUP_ORDER.filter((label) => groups.has(label)).map((label) => ({
    label,
    sessions: groups.get(label) || [],
  }));
}

export function formatSessionUpdatedAt(updatedAt: string, reference = new Date()): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) return updatedAt;
  const group = getHistoryGroupLabel(updatedAt, reference);
  const time = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);

  if (group === 'Today') return time;
  if (group === 'Yesterday') return `Yesterday, ${time}`;
  if (group === 'Previous 7 days') {
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'short',
      hour: 'numeric',
      minute: '2-digit',
    }).format(date);
  }
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() === reference.getFullYear() ? undefined : 'numeric',
  }).format(date);
}
