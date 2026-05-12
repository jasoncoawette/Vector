// Backend base URL.
// - When the frontend is served by the backend (single-process deploy),
//   the bundle and the API share an origin, so '' (relative URLs) is correct.
// - When SvelteKit dev server is running on :5173, we hit the backend
//   at :7777 directly. The Vite env var VITE_BACKEND lets you point at
//   a different host (e.g. a Mac mini's Tailscale name).
// - In browser contexts where neither holds, fall back to loopback.
const BACKEND: string = (() => {
  const env = (import.meta as any)?.env?.VITE_BACKEND;
  if (typeof env === 'string' && env) return env;
  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location;
    // Served by the backend itself: same origin, empty prefix.
    if (port !== '5173') return '';
    // SvelteKit dev server: assume the backend is on :7777 of the same host.
    return `${protocol}//${hostname}:7777`;
  }
  return 'http://127.0.0.1:7777';
})();

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
  // Same-origin deploy: the API rides on whatever host loaded the bundle.
  // Trust the page's own hostname.
  let target: string;
  if (BACKEND === '') {
    if (typeof window === 'undefined') return false;
    target = window.location.origin;
  } else {
    target = BACKEND;
  }
  try {
    const u = new URL(target);
    if (u.hostname === '127.0.0.1' || u.hostname === 'localhost') return true;
    if (u.hostname.startsWith('100.')) return true; // Tailscale CGNAT
    return false;
  } catch {
    return false;
  }
}

export interface RoutingTier {
  tier: 'haiku' | 'sonnet' | 'opus';
  decisions: number;
  successes: number;
  failures: number;
  pending: number;
  mean_cost_usd: number;
  success_rate: number;
  alpha: number;
  beta: number;
  trials: number;
  mean_reward: number;
}

export interface RoutingStats {
  tiers: RoutingTier[];
}

export interface RoutingLogEntry {
  ts: number;
  agent_type: string | null;
  tier: 'haiku' | 'sonnet' | 'opus';
  model: string;
  score: number;
  source: 'heuristic' | 'bandit' | 'override';
  outcome: 0 | 1 | null;
  cost_usd: number | null;
}

export async function fetchRoutingStats(
  fetcher: typeof fetch = fetch
): Promise<RoutingStats> {
  const r = await fetcher(`${BACKEND}/routing/stats`);
  if (!r.ok) throw new Error(`routing stats failed: ${r.status}`);
  return (await r.json()) as RoutingStats;
}

export async function fetchRoutingLog(
  limit = 100,
  fetcher: typeof fetch = fetch
): Promise<RoutingLogEntry[]> {
  const r = await fetcher(`${BACKEND}/routing/log?limit=${limit}`);
  if (!r.ok) throw new Error(`routing log failed: ${r.status}`);
  const body = (await r.json()) as { entries: RoutingLogEntry[] };
  return body.entries;
}

export interface CostDay {
  day: string;
  total_usd: number;
  runs: number;
  by_type: Record<string, number>;
}

export interface CostTier {
  tier: 'haiku' | 'sonnet' | 'opus';
  decisions: number;
  total_usd: number;
  mean_usd: number;
}

export interface CostSummary {
  today_usd: number;
  today_runs: number;
  week_usd: number;
  week_runs: number;
  month_usd: number;
  month_runs: number;
  daily_budget_usd: number;
  over_budget_today: boolean;
  daily: CostDay[];
  by_tier: CostTier[];
}

export async function fetchCosts(
  historyDays = 14,
  fetcher: typeof fetch = fetch
): Promise<CostSummary> {
  const r = await fetcher(`${BACKEND}/costs?history_days=${historyDays}`);
  if (!r.ok) throw new Error(`costs failed: ${r.status}`);
  return (await r.json()) as CostSummary;
}

// Plans / DAG ----------------------------------------------------------

export type PlanStepAgent =
  | 'code'
  | 'research'
  | 'writer'
  | 'tester'
  | 'security';
export type PlanStepStatus =
  | 'pending'
  | 'ready'
  | 'running'
  | 'done'
  | 'failed'
  | 'skipped';
export type PlanStatus = 'pending' | 'running' | 'done' | 'failed' | 'partial';

export interface PlanStepDef {
  id: number;
  agent: PlanStepAgent;
  prompt: string;
  depends_on: number[];
  files: string[];
  success_criteria: string | null;
  cost_cap_usd: number;
  timeout_s: number;
  max_attempts: number;
}

export interface PlanDef {
  id: string;
  goal: string;
  created_at: number;
  steps: PlanStepDef[];
}

export interface StepRunSnapshot {
  step_id: number;
  status: PlanStepStatus;
  output: string;
  error: string;
  cost_usd: number;
  run_id: string | null;
  started_at: number | null;
  ended_at: number | null;
}

export interface PlanRunSnapshot {
  plan: PlanDef;
  status: PlanStatus;
  steps: StepRunSnapshot[];
  total_cost_usd: number;
  started_at: number | null;
  ended_at: number | null;
  error: string;
}

export interface NewPlanStep {
  id: number;
  agent: PlanStepAgent;
  prompt: string;
  depends_on?: number[];
  success_criteria?: string;
}

export interface NewPlan {
  goal: string;
  steps: NewPlanStep[];
}

export async function listPlans(
  fetcher: typeof fetch = fetch
): Promise<PlanRunSnapshot[]> {
  const r = await fetcher(`${BACKEND}/plans`);
  if (!r.ok) throw new Error(`list plans failed: ${r.status}`);
  const body = (await r.json()) as { plans: PlanRunSnapshot[] };
  return body.plans;
}

export async function fetchPlan(
  planId: string,
  fetcher: typeof fetch = fetch
): Promise<PlanRunSnapshot> {
  const r = await fetcher(`${BACKEND}/plans/${encodeURIComponent(planId)}`);
  if (!r.ok) throw new Error(`fetch plan failed: ${r.status}`);
  return (await r.json()) as PlanRunSnapshot;
}

export async function submitPlan(
  plan: NewPlan,
  token: string | null = null,
  fetcher: typeof fetch = fetch
): Promise<PlanRunSnapshot> {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetcher(`${BACKEND}/plans`, {
    method: 'POST',
    headers,
    body: JSON.stringify(plan)
  });
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`submit plan failed: ${r.status} ${text}`);
  }
  return (await r.json()) as PlanRunSnapshot;
}
