<script lang="ts">
  // Zero-UI poller that drains /voice/inbox every 60s while the tab is
  // visible. Calls `onmessage` for each new brief; on a successful return
  // it acks the message so the backend won't replay it. A failed callback
  // OR a failed ack leaves the row pending — the next tick retries.
  //
  // Pause-on-hidden is a hard requirement (RES-44): we listen for
  // visibilitychange and clear/restart the interval accordingly.

  import { onMount, onDestroy } from 'svelte';
  import { fetchPending, ack, type InboxMessage } from '$lib/inbox';

  export let onmessage: (msg: InboxMessage) => Promise<void> | void = async () => {};
  /** Poll cadence in ms. Overridable so tests can use fake timers. */
  export let intervalMs: number = 60_000;

  let timer: ReturnType<typeof setInterval> | null = null;
  /** In-flight ids to dedupe within and across overlapping ticks. */
  const seen: Set<number> = new Set();

  function isVisible(): boolean {
    if (typeof document === 'undefined') return true;
    return document.visibilityState === 'visible';
  }

  async function tick(): Promise<void> {
    if (!isVisible()) return;
    let messages: InboxMessage[];
    try {
      messages = await fetchPending();
    } catch {
      // fetchPending already swallows errors, but be defensive.
      return;
    }
    for (const msg of messages) {
      if (seen.has(msg.id)) continue;
      seen.add(msg.id);
      try {
        await onmessage(msg);
        // Only ack after the caller has played / displayed the brief.
        await ack(msg.id);
      } catch {
        // Either the callback or the ack failed. Drop the id from `seen`
        // so the next tick treats it as new and retries — never silently
        // swallow (RES-44 hard rule).
        seen.delete(msg.id);
      }
    }
  }

  function start(): void {
    if (timer !== null) return;
    // Fire one tick immediately so a freshly-queued brief doesn't wait
    // a full minute, then settle into the cadence.
    void tick();
    timer = setInterval(() => {
      void tick();
    }, intervalMs);
  }

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function onVisibilityChange(): void {
    if (isVisible()) start();
    else stop();
  }

  onMount(() => {
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange);
    }
    if (isVisible()) start();
  });

  onDestroy(() => {
    stop();
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    }
  });
</script>
