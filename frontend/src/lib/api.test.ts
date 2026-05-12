import { describe, it, expect, vi, beforeEach } from 'vitest';
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

describe('cache helpers', () => {
  beforeEach(() => {
    if (typeof localStorage !== 'undefined') localStorage.clear();
  });

  it('saves and loads typed values', async () => {
    const { cacheSave, cacheLoad } = await import('./api');
    cacheSave('k', { hello: 'world' });
    const r = cacheLoad<{ hello: string }>('k');
    expect(r?.value.hello).toBe('world');
    expect(r?.ageMs).toBeGreaterThanOrEqual(0);
  });

  it('returns null on missing key', async () => {
    const { cacheLoad } = await import('./api');
    expect(cacheLoad('missing')).toBeNull();
  });

  it('isCacheStale honors 24h horizon', async () => {
    const { isCacheStale } = await import('./api');
    expect(isCacheStale(60 * 60 * 1000)).toBe(false);
    expect(isCacheStale(48 * 60 * 60 * 1000)).toBe(true);
  });

  it('isLocalBackend accepts loopback', async () => {
    const { isLocalBackend } = await import('./api');
    expect(isLocalBackend()).toBe(true);
  });
});

describe('audit api', () => {
  it('fetches and parses entries', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        entries: [
          {
            ts: 1,
            tool: 'file.read',
            caller: 'u',
            args_hash: 'a',
            result_hash: 'b',
            ok: true,
            reason: null
          }
        ]
      })
    });
    const { fetchAudit } = await import('./api');
    const r = await fetchAudit(10, fakeFetch as unknown as typeof fetch);
    expect(r[0].tool).toBe('file.read');
  });
});

describe('routing api', () => {
  it('fetchRoutingStats returns tiers', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        tiers: [
          {
            tier: 'haiku',
            decisions: 12,
            successes: 10,
            failures: 2,
            pending: 0,
            mean_cost_usd: 0.0012,
            success_rate: 0.83,
            alpha: 11,
            beta: 3,
            trials: 12,
            mean_reward: 0.79
          }
        ]
      })
    });
    const { fetchRoutingStats } = await import('./api');
    const r = await fetchRoutingStats(fakeFetch as unknown as typeof fetch);
    expect(r.tiers[0].tier).toBe('haiku');
    expect(r.tiers[0].trials).toBe(12);
  });

  it('fetchRoutingLog clamps limit in URL', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ entries: [] })
    });
    const { fetchRoutingLog } = await import('./api');
    await fetchRoutingLog(50, fakeFetch as unknown as typeof fetch);
    expect(fakeFetch).toHaveBeenCalledWith(expect.stringContaining('limit=50'));
  });

  it('fetchRoutingStats throws on error', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    const { fetchRoutingStats } = await import('./api');
    await expect(
      fetchRoutingStats(fakeFetch as unknown as typeof fetch)
    ).rejects.toThrow();
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
