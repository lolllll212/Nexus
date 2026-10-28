import type {
  ChatCodingMetadata,
  ChatEffort,
  ChatExecutionMetadata,
  ChatQualityMetadata,
  CodingFocus,
  NexusTool,
  NexusToolApproval,
  UpgradeSpacesResponse,
} from './types';

const configuredKey = import.meta.env.VITE_NEXUS_API_KEY as string | undefined;
const API_KEY_STORAGE_KEY = 'nexus_api_key';
const DEFAULT_API_KEY = 'sk-local-dev';

function getStoredApiKey(): string | null {
  try {
    return localStorage.getItem(API_KEY_STORAGE_KEY);
  } catch {
    return null;
  }
}

function getFallbackApiKey(): string {
  return configuredKey || DEFAULT_API_KEY;
}

function clearStoredApiKey(): void {
  try {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
}

export function getApiKey(): string {
  return getStoredApiKey() || getFallbackApiKey();
}

export function setApiKey(value: string): void {
  const trimmed = value.trim();
  try {
    if (trimmed) localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
    else localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // Ignore storage failures; the configured/default key remains usable.
  }
}

function canRetryRequestBody(body: BodyInit | null | undefined): boolean {
  return (
    body == null ||
    typeof body === 'string' ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

async function fetchWithApiKey(
  input: RequestInfo | URL,
  init: RequestInit,
  apiKey: string,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${apiKey}`);
  // FormData bodies set their own multipart boundary — never force JSON on them.
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return fetch(input, { ...init, headers });
}

export async function nexusFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const storedKey = getStoredApiKey();
  const fallbackKey = getFallbackApiKey();
  const activeKey = storedKey || fallbackKey;

  let response = await fetchWithApiKey(input, init, activeKey);

  // A browser can outlive a sandbox/API-key rotation. If a saved key is stale,
  // clear it and retry once with the deployment-configured/default key so the
  // chat preview recovers without asking the user to clear site data manually.
  if (
    response.status === 401 &&
    storedKey &&
    storedKey !== fallbackKey &&
    canRetryRequestBody(init.body)
  ) {
    clearStoredApiKey();
    response = await fetchWithApiKey(input, init, fallbackKey);
  }

  if (response.status === 401) {
    throw new Error('NEXUS authentication failed. Configure a valid API key in local storage.');
  }
  return response;
}

export async function nexusJson<T>(input: RequestInfo | URL, init: RequestInit = {}): Promise<T> {
  const response = await nexusFetch(input, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

// ── Tool registry: the chat agent receives this same catalog through the
// backend ReAct loop; these helpers let the Claude-style workspace display,
// approve, and (for admins) run individual tools directly. ─────────────────
export async function fetchNexusTools(): Promise<NexusTool[]> {
  return nexusJson<NexusTool[]>('/v1/tools');
}

export async function fetchToolApprovals(): Promise<NexusToolApproval[]> {
  return nexusJson<NexusToolApproval[]>('/v1/tools/approvals');
}

export async function grantToolApprovals(toolIds: string[]): Promise<NexusToolApproval[]> {
  return nexusJson<NexusToolApproval[]>('/v1/tools/approvals/grant', {
    method: 'POST',
    body: JSON.stringify({ tool_ids: toolIds }),
  });
}

export async function executeNexusTool(
  toolId: string,
  params: Record<string, any>,
  signal?: AbortSignal,
): Promise<{ tool_id: string; result: Record<string, any> }> {
  return nexusJson<{ tool_id: string; result: Record<string, any> }>('/v1/tools/execute', {
    method: 'POST',
    body: JSON.stringify({ tool_id: toolId, params }),
    signal,
  });
}

export async function fetchUpgradeSpaces(signal?: AbortSignal): Promise<UpgradeSpacesResponse> {
  return nexusJson<UpgradeSpacesResponse>('/api/system/upgrade-spaces', { signal });
}

export interface ChatStreamEvent {
  type: string;
  content?: string;
  tool_id?: string;
  session_id?: string | null;
  model?: string;
  model_source?: string;
  provider_status?: string;
  effort?: ChatEffort;
  mode?: string;
  coding_focus?: CodingFocus;
  attempt?: number;
  issues?: string[];
  execution?: ChatExecutionMetadata;
  quality?: ChatQualityMetadata;
  coding?: ChatCodingMetadata;
  response_id?: string;
  guardrail?: Record<string, unknown>;
  context_sources?: Array<Record<string, unknown>>;
}

export interface NexusChatOptions {
  /** Model changer selection: 'auto' or a NVIDIA NIM model id. */
  model?: string;
  /** Adaptive execution effort: auto, fast, balanced, deep, or max. */
  effort?: ChatEffort;
  /** Frontend/language specialist focus for this request. */
  codingFocus?: CodingFocus;
  /** Cortex session id for conversational memory continuity. */
  sessionId?: string;
  /** Claude-style capability toggles. */
  extendedThinking?: boolean;
  deepResearch?: boolean;
  artifacts?: boolean;
  /** Aborts the HTTP request and its event-stream reader (Stop generating). */
  signal?: AbortSignal;
}

export async function nexusChatStream(
  message: string,
  mode: string,
  onEvent: (event: ChatStreamEvent) => void,
  options: NexusChatOptions = {},
): Promise<void> {
  const payload: Record<string, unknown> = { message, mode };
  if (options.sessionId) payload.session_id = options.sessionId;
  if (options.model) payload.model = options.model;
  if (options.effort) payload.effort = options.effort;
  if (options.codingFocus) payload.coding_focus = options.codingFocus;
  if (options.extendedThinking !== undefined) payload.extended_thinking = options.extendedThinking;
  if (options.deepResearch !== undefined) payload.deep_research = options.deepResearch;
  if (options.artifacts !== undefined) payload.artifacts = options.artifacts;

  const response = await nexusFetch('/v1/chat/stream', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload?.detail === 'string' ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  if (!response.body) throw new Error('NEXUS returned an empty event stream.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = false;

  const consumeFrame = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) return;
    if (data === '[DONE]') {
      completed = true;
      return;
    }

    let event: ChatStreamEvent;
    try {
      event = JSON.parse(data) as ChatStreamEvent;
    } catch {
      throw new Error('NEXUS returned an invalid event-stream frame.');
    }
    if (event.type === 'error') {
      throw new Error(event.content || 'NEXUS stream failed.');
    }
    onEvent(event);
    if (event.type === 'done') completed = true;
  };

  try {
    while (!completed) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const separator = /\r?\n\r?\n/;
      let match: RegExpExecArray | null;
      while ((match = separator.exec(buffer)) !== null) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        consumeFrame(frame);
        if (completed) break;
      }
      if (done) {
        if (buffer.trim()) consumeFrame(buffer);
        break;
      }
    }
  } finally {
    if (options.signal?.aborted) {
      await reader.cancel().catch(() => undefined);
    }
    reader.releaseLock();
  }

  if (!completed) throw new Error('NEXUS event stream ended before its done event.');
}
