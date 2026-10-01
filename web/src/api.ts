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
