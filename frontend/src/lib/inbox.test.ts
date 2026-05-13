import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchPending, ack, streamTts } from './inbox';

describe('fetchPending', () => {
  it('returns messages array on 200', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        messages: [
          {
            id: 1,
            kind: 'brief',
            text: 'Three picks today.',
            meta: {},
            created_at: 1000
          }
        ]
      })
    });
    const out = await fetchPending(
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe(1);
    expect(out[0].text).toContain('picks');
  });

  it('returns [] on 404 instead of throwing', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    const out = await fetchPending(
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toEqual([]);
  });

  it('returns [] when fetch rejects (network down)', async () => {
    const fakeFetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const out = await fetchPending(
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toEqual([]);
  });

  it('returns [] when payload is missing the messages key', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({})
    });
    const out = await fetchPending(
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toEqual([]);
  });
});

describe('ack', () => {
  beforeEach(() => {
    if (typeof localStorage !== 'undefined') localStorage.clear();
  });

  it('sends POST to /voice/inbox/{id}/ack', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ delivered: true })
    });
    await ack(42, 'http://x', fakeFetch as unknown as typeof fetch);
    const call = fakeFetch.mock.calls[0];
    expect(call[0]).toContain('/voice/inbox/42/ack');
    expect(call[1].method).toBe('POST');
  });

  it('attaches bearer token from localStorage when present', async () => {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('vector.token', 'mytok');
    }
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ delivered: true })
    });
    await ack(7, 'http://x', fakeFetch as unknown as typeof fetch);
    const call = fakeFetch.mock.calls[0];
    expect(call[1].headers['Authorization']).toBe('Bearer mytok');
  });

  it('throws on non-2xx so the watcher leaves the row pending', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    await expect(
      ack(1, 'http://x', fakeFetch as unknown as typeof fetch)
    ).rejects.toThrow();
  });
});

describe('streamTts', () => {
  it('returns null when /tts/stream 404s (fall back to text)', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    const out = await streamTts(
      'hello',
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toBeNull();
  });

  it('returns null when fetch rejects', async () => {
    const fakeFetch = vi.fn().mockRejectedValue(new Error('boom'));
    const out = await streamTts(
      'hello',
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).toBeNull();
  });

  it('returns an HTMLAudioElement on 200', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    const out = await streamTts(
      'hi there',
      'http://x',
      fakeFetch as unknown as typeof fetch
    );
    expect(out).not.toBeNull();
    // jsdom Audio is an HTMLAudioElement; we expect the URL to contain
    // the encoded text so the eventual <audio> tag plays the right thing.
    expect((out as HTMLAudioElement).src).toContain('text=hi%20there');
  });
});
