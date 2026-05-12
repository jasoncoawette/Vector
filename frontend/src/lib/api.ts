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
