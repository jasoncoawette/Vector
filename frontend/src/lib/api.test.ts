import { describe, it, expect, vi } from 'vitest';
import { fetchBrief, fetchGreeting, fetchMetrics } from './api';

describe('fetchGreeting', () => {
  it('returns greeting payload on 200', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ text: 'Good morning Jason.', user: 'Jason' })
    });
    const r = await fetchGreeting(fakeFetch as unknown as typeof fetch);
    expect(r.user).toBe('Jason');
    expect(r.text).toContain('Jason');
  });

  it('throws on non-200', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    await expect(fetchGreeting(fakeFetch as unknown as typeof fetch)).rejects.toThrow();
  });
});

describe('fetchMetrics', () => {
  it('returns sections payload', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        sections: {
          stratus: [
            { name: 'revenue', value: 1000, unit: 'usd', recorded_at: 1, stale: false }
          ]
        }
      })
    });
    const r = await fetchMetrics(fakeFetch as unknown as typeof fetch);
    expect(r.sections.stratus[0].name).toBe('revenue');
  });
});

describe('fetchBrief', () => {
  it('returns spoken text', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ text: 'Three picks today.', picks: 3 })
    });
    const r = await fetchBrief(fakeFetch as unknown as typeof fetch);
    expect(r.picks).toBe(3);
  });
});
