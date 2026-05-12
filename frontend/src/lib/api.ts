const BACKEND = 'http://127.0.0.1:7777';

export interface Greeting {
  text: string;
  user: string;
}

export interface MetricPoint {
  name: string;
  value: number;
  unit: string | null;
  recorded_at: number;
  stale: boolean;
}

export interface MetricsResponse {
  sections: Record<string, MetricPoint[]>;
}

export interface Pick {
  task_id: number;
  title: string;
  score: number;
  reason: string;
}

export async function fetchGreeting(fetcher: typeof fetch = fetch): Promise<Greeting> {
  const r = await fetcher(`${BACKEND}/voice/greeting`);
  if (!r.ok) throw new Error(`greeting failed: ${r.status}`);
  return (await r.json()) as Greeting;
}

export async function fetchMetrics(fetcher: typeof fetch = fetch): Promise<MetricsResponse> {
  const r = await fetcher(`${BACKEND}/metrics`);
  if (!r.ok) throw new Error(`metrics failed: ${r.status}`);
  return (await r.json()) as MetricsResponse;
}

export async function fetchBrief(
  fetcher: typeof fetch = fetch
): Promise<{ text: string; picks: number }> {
  const r = await fetcher(`${BACKEND}/daily/brief`);
  if (!r.ok) throw new Error(`brief failed: ${r.status}`);
  return (await r.json()) as { text: string; picks: number };
}

export type AgentType = 'code' | 'research' | 'writer';
export type RunStatus =
  | 'queued'
  | 'running'
  | 'done'
  | 'failed'
  | 'killed'
  | 'needs_confirm';

export interface AgentRun {
  id: string;
  type: AgentType;
  prompt: string;
  status: RunStatus;
  cost_usd: number;
  fallback_used: boolean;
  elapsed_s: number;
  long_running: boolean;
  files: string[];
  output: string;
  error: string;
}

export async function listAgents(
  fetcher: typeof fetch = fetch
): Promise<AgentRun[]> {
  const r = await fetcher(`${BACKEND}/agents`);
  if (!r.ok) throw new Error(`agents failed: ${r.status}`);
  const body = (await r.json()) as { runs: AgentRun[] };
  return body.runs;
}

export async function spawnAgent(
  body: {
    type: AgentType;
    prompt: string;
    files?: string[];
    cost_cap_usd?: number;
    timeout_s?: number;
  },
  fetcher: typeof fetch = fetch
): Promise<AgentRun> {
  const r = await fetcher(`${BACKEND}/agents/spawn`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`spawn failed: ${r.status}`);
  return (await r.json()) as AgentRun;
}

export async function killAgent(
  id: string,
  reason = 'killed by user',
  fetcher: typeof fetch = fetch
): Promise<boolean> {
  const r = await fetcher(`${BACKEND}/agents/${id}/kill`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ reason })
  });
  if (!r.ok) throw new Error(`kill failed: ${r.status}`);
  return ((await r.json()) as { killed: boolean }).killed;
}

export interface AuditEntry {
  ts: number;
  tool: string;
  caller: string;
  args_hash: string;
  result_hash: string;
  ok: boolean;
  reason: string | null;
}

export async function fetchAudit(
  limit = 50,
  fetcher: typeof fetch = fetch
): Promise<AuditEntry[]> {
  const r = await fetcher(`${BACKEND}/audit?limit=${limit}`);
  if (!r.ok) throw new Error(`audit failed: ${r.status}`);
  const body = (await r.json()) as { entries: AuditEntry[] };
  return body.entries;
}

export interface MissionPoint {
  value: number;
  recorded_at: number;
}

export interface ChokePoint {
  rank: number;
  title: string;
  note: string | null;
}

export interface MissionResponse {
  week: string;
  series: Record<string, MissionPoint[]>;
  choke_points: ChokePoint[];
}

export async function fetchMission(
  fetcher: typeof fetch = fetch
): Promise<MissionResponse> {
  const r = await fetcher(`${BACKEND}/mission`);
  if (!r.ok) throw new Error(`mission failed: ${r.status}`);
  return (await r.json()) as MissionResponse;
}

const CACHE_PREFIX = 'vector.cache.';
const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function cacheSave<T>(key: string, value: T): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(
    CACHE_PREFIX + key,
    JSON.stringify({ ts: Date.now(), value })
  );
}

export function cacheLoad<T>(key: string): { value: T; ageMs: number } | null {
  if (typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(CACHE_PREFIX + key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { ts: number; value: T };
    return { value: parsed.value, ageMs: Date.now() - parsed.ts };
  } catch {
    return null;
  }
}

export function isCacheStale(ageMs: number): boolean {
  return ageMs > STALE_AFTER_MS;
}

export function isLocalBackend(): boolean {
  try {
    const u = new URL(BACKEND);
    if (u.hostname === '127.0.0.1' || u.hostname === 'localhost') return true;
    if (u.hostname.startsWith('100.')) return true;
    return false;
  } catch {
    return false;
  }
}
