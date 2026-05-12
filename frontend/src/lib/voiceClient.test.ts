import { describe, it, expect, beforeEach } from 'vitest';
import { buildVoiceUrl } from './voiceClient';

describe('buildVoiceUrl', () => {
  beforeEach(() => {
    // jsdom default origin is http://localhost
  });

  it('converts http backend to ws URL', () => {
    expect(buildVoiceUrl('http://127.0.0.1:7777', null)).toBe(
      'ws://127.0.0.1:7777/voice/stream'
    );
  });

  it('converts https backend to wss URL', () => {
    expect(buildVoiceUrl('https://mac-mini.tail-scale.ts.net:7777', null)).toBe(
      'wss://mac-mini.tail-scale.ts.net:7777/voice/stream'
    );
  });

  it('appends bearer token when provided', () => {
    const url = buildVoiceUrl('http://127.0.0.1:7777', 'abc123');
    expect(url).toContain('?token=abc123');
  });

  it('omits token when null', () => {
    const url = buildVoiceUrl('http://127.0.0.1:7777', null);
    expect(url).not.toContain('token');
  });

  it('uses window.location when backend is empty string', () => {
    const url = buildVoiceUrl('', 'tok');
    // jsdom origin defaults to http://localhost
    expect(url.startsWith('ws://')).toBe(true);
    expect(url).toContain('/voice/stream');
    expect(url).toContain('token=tok');
  });
});
