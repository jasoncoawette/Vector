// Voice inbox client — drains the backend's /voice/inbox queue (RES-43)
// and ships each rendered message through TTS or text-fallback.
//
// Backend contract (from backend/vector/app.py):
//   GET  /voice/inbox            -> {messages: [{id, kind, text, meta, created_at, ...}]}
//   POST /voice/inbox/{id}/ack   -> {delivered: true}   (requires bearer)
//
// We deliberately swallow GET errors so a flaky network or temporary 5xx
// doesn't poison the watcher loop — the next tick just retries. ACK errors
// DO throw so the watcher leaves the message unacked and retries it on the
// next tick (per RES-44 hard rules).

export type InboxMessage = {
  id: number;
  kind: string;
  text: string;
  meta: Record<string, unknown>;
  created_at: number;
};

// Mirror the BACKEND resolution from api.ts so the module agrees with the
// rest of the frontend on where the API lives. Keep it inline rather than
// reaching into api.ts to avoid creating a circular import or leaking an
// internal helper.
function defaultBackend(): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const env = (import.meta as any)?.env?.VITE_BACKEND;
  if (typeof env === 'string' && env) return env;
  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location;
    if (port !== '5173') return '';
    return `${protocol}//${hostname}:7777`;
  }
  return 'http://127.0.0.1:7777';
}

function bearerToken(): string | null {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fromEnv = (import.meta as any)?.env?.VITE_BACKEND_BEARER as
    | string
    | undefined;
  if (typeof fromEnv === 'string' && fromEnv) return fromEnv;
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem('vector.token');
    if (stored) return stored;
  }
  return null;
}

export async function fetchPending(
  baseUrl?: string,
  fetcher: typeof fetch = fetch
): Promise<InboxMessage[]> {
  const base = baseUrl ?? defaultBackend();
  try {
    const r = await fetcher(`${base}/voice/inbox`);
    if (!r.ok) return [];
    const body = (await r.json()) as { messages?: InboxMessage[] };
    return Array.isArray(body.messages) ? body.messages : [];
  } catch {
    // Network failure: swallow, the next poll tick retries.
    return [];
  }
}

export async function ack(
  id: number,
  baseUrl?: string,
  fetcher: typeof fetch = fetch
): Promise<void> {
  const base = baseUrl ?? defaultBackend();
  const headers: Record<string, string> = {};
  const token = bearerToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetcher(`${base}/voice/inbox/${id}/ack`, {
    method: 'POST',
    headers
  });
  if (!r.ok) {
    throw new Error(`ack ${id} failed: ${r.status}`);
  }
}

export async function streamTts(
  text: string,
  baseUrl?: string,
  fetcher: typeof fetch = fetch
): Promise<HTMLAudioElement | null> {
  // The /tts/stream endpoint doesn't exist yet — backend TTS lives behind
  // the WebSocket session. We probe the HTTP path so when it lands we can
  // play through it; until then the 404 means "fall back to text-only".
  if (typeof Audio === 'undefined') return null;
  const base = baseUrl ?? defaultBackend();
  const url = `${base}/tts/stream?text=${encodeURIComponent(text)}`;
  try {
    const r = await fetcher(url);
    if (!r.ok) return null;
    const audio = new Audio(url);
    return audio;
  } catch {
    return null;
  }
}
