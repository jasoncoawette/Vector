// Tiny store for displaying delivered briefs in the voice transcript area.
// VoiceInboxWatcher's onmessage handler appends to this; the voice page
// renders it. Kept separate from voiceState so the existing live-voice
// state machine doesn't get tangled with the async push channel.

import { writable, type Writable } from 'svelte/store';
import type { InboxMessage } from '../inbox';

export const briefs: Writable<InboxMessage[]> = writable([]);

export function appendBrief(msg: InboxMessage): void {
  briefs.update((list) => {
    // Guard against the watcher seeing the same id twice across remounts.
    if (list.some((m) => m.id === msg.id)) return list;
    return [...list, msg];
  });
}

export function clearBriefs(): void {
  briefs.set([]);
}
