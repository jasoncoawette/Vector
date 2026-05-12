import { writable, derived, type Readable } from 'svelte/store';

export type VoiceState = 'idle' | 'listen' | 'think' | 'speak' | 'error';

export const STATE_COLORS: Record<VoiceState, number> = {
  idle: 0x3b82f6,
  listen: 0x22c55e,
  think: 0xeab308,
  speak: 0xffffff,
  error: 0xef4444
};

const validTransitions: Record<VoiceState, VoiceState[]> = {
  idle: ['listen', 'error'],
  listen: ['think', 'idle', 'error'],
  think: ['speak', 'idle', 'error'],
  speak: ['listen', 'idle', 'error'],
  error: ['idle']
};

function createVoiceStore() {
  const state = writable<VoiceState>('idle');
  const muted = writable(false);

  function transition(next: VoiceState) {
    state.update((current) => {
      if (next === 'error') return 'error';
      const allowed = validTransitions[current];
      if (!allowed.includes(next)) return current;
      return next;
    });
  }

  return {
    state: { subscribe: state.subscribe } as Readable<VoiceState>,
    muted: { subscribe: muted.subscribe } as Readable<boolean>,
    toListen: () => {
      let isMuted = false;
      muted.subscribe((v) => (isMuted = v))();
      if (!isMuted) transition('listen');
    },
    toThink: () => transition('think'),
    toSpeak: () => transition('speak'),
    toIdle: () => transition('idle'),
    toError: () => transition('error'),
    bargeIn: () => {
      state.update((current) => (current === 'speak' ? 'listen' : current));
    },
    setMuted: (value: boolean) => muted.set(value),
    toggleMute: () => muted.update((v) => !v)
  };
}

export const voice = createVoiceStore();

export const orbColor: Readable<number> = derived(voice.state, ($s) => STATE_COLORS[$s]);
