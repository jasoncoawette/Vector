const BACKEND = 'http://127.0.0.1:7777';

export interface Greeting {
  text: string;
  user: string;
}

export async function fetchGreeting(fetcher: typeof fetch = fetch): Promise<Greeting> {
  const r = await fetcher(`${BACKEND}/voice/greeting`);
  if (!r.ok) throw new Error(`greeting failed: ${r.status}`);
  return (await r.json()) as Greeting;
}
