import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { voice } from './voiceState';

function snapshot() {
  return get(voice.state);
}

beforeEach(() => {
  voice.setMuted(false);
  voice.toIdle();
});

describe('voiceState', () => {
  it('starts idle', () => {
    expect(snapshot()).toBe('idle');
  });

  it('walks idle -> listen -> think -> speak -> idle', () => {
    voice.toListen();
    expect(snapshot()).toBe('listen');
    voice.toThink();
    expect(snapshot()).toBe('think');
    voice.toSpeak();
    expect(snapshot()).toBe('speak');
    voice.toIdle();
    expect(snapshot()).toBe('idle');
  });

  it('error is reachable from any state', () => {
    voice.toListen();
    voice.toError();
    expect(snapshot()).toBe('error');
  });

  it('barge-in moves speak -> listen', () => {
    voice.toListen();
    voice.toThink();
    voice.toSpeak();
    voice.bargeIn();
    expect(snapshot()).toBe('listen');
  });

  it('mute blocks listen transition', () => {
    voice.setMuted(true);
    voice.toListen();
    expect(snapshot()).toBe('idle');
  });

  it('rejects invalid transitions', () => {
    voice.toSpeak();
    expect(snapshot()).toBe('idle');
  });
});
