import { describe, it, expect, vi } from 'vitest';
import { fetchGreeting } from './api';

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
