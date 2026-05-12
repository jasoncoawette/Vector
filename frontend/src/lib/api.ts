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
