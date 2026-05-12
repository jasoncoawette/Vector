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

describe('agents api', () => {
  it('listAgents returns runs array', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        runs: [
          {
            id: 'a',
            type: 'code',
            prompt: 'p',
            status: 'done',
            cost_usd: 0.1,
            fallback_used: false,
            elapsed_s: 1.2,
            long_running: false,
            files: [],
            output: 'out',
            error: ''
          }
        ]
      })
    });
    const { listAgents } = await import('./api');
    const r = await listAgents(fakeFetch as unknown as typeof fetch);
    expect(r[0].id).toBe('a');
  });

  it('spawnAgent posts JSON', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: 'b',
        type: 'research',
        prompt: 'go',
        status: 'queued',
        cost_usd: 0,
        fallback_used: false,
        elapsed_s: 0,
        long_running: false,
        files: [],
        output: '',
        error: ''
      })
    });
    const { spawnAgent } = await import('./api');
    const r = await spawnAgent(
      { type: 'research', prompt: 'go' },
      fakeFetch as unknown as typeof fetch
    );
    expect(r.id).toBe('b');
    expect(fakeFetch).toHaveBeenCalledWith(
      expect.stringContaining('/agents/spawn'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('killAgent posts reason', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ killed: true })
    });
    const { killAgent } = await import('./api');
    const r = await killAgent('id1', 'off topic', fakeFetch as unknown as typeof fetch);
    expect(r).toBe(true);
  });
});
