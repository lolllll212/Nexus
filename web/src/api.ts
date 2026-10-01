const configuredKey = import.meta.env.VITE_NEXUS_API_KEY as string | undefined;

export function getApiKey(): string {
  return localStorage.getItem('nexus_api_key') || configuredKey || 'sk-local-dev';
}

export function setApiKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) localStorage.setItem('nexus_api_key', trimmed);
  else localStorage.removeItem('nexus_api_key');
}

export async function nexusFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${getApiKey()}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  const response = await fetch(input, { ...init, headers });
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

export interface ChatStreamEvent {
  type: string;
  content?: string;
  tool_id?: string;
  session_id?: string | null;
}

export async function nexusChatStream(
  message: string,
  mode: 'general' | 'coding',
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const response = await nexusFetch('/v1/chat/stream', {
    method: 'POST',
    body: JSON.stringify({ message, mode }),
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
    reader.releaseLock();
  }

  if (!completed) throw new Error('NEXUS event stream ended before its done event.');
}
