<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Orb from '$lib/Orb.svelte';
  import { voice } from '$lib/voiceState';
  import { buildVoiceUrl, VoiceClient, type VoiceEvent } from '$lib/voiceClient';

  // Reuses BACKEND resolution from api.ts.
  const BACKEND: string = (() => {
    const env = (import.meta as any)?.env?.VITE_BACKEND;
    if (typeof env === 'string' && env) return env;
    if (typeof window !== 'undefined') {
      const { protocol, hostname, port } = window.location;
      if (port !== '5173') return '';
      return `${protocol}//${hostname}:7777`;
    }
    return 'http://127.0.0.1:7777';
  })();

  // Bearer token (optional). Stored in localStorage so the user only
  // pastes it once. For loopback or dev with VECTOR_BACKEND_BEARER unset
  // this stays empty and the backend accepts the connection.
  let token = '';
  let pttDown = false;
  let connecting = false;
  let connected = false;
  let transcript = '';
  let reply = '';
  let error = '';

  let client: VoiceClient | null = null;

  function loadToken() {
    if (typeof localStorage !== 'undefined') {
      token = localStorage.getItem('vector.token') ?? '';
    }
  }
  function saveToken(t: string) {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('vector.token', t);
    }
  }

  async function connect() {
    if (connected || connecting) return;
    connecting = true;
    error = '';
    try {
      const url = buildVoiceUrl(BACKEND, token || null);
      client = new VoiceClient({
        url,
        onEvent: handleEvent,
        onClose: () => {
          connected = false;
          voice.toIdle();
        }
      });
      await client.connect();
      connected = true;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      connecting = false;
    }
  }

  function handleEvent(e: VoiceEvent) {
    if (e.kind === 'state' && e.state) {
      switch (e.state) {
        case 'listen':
          voice.toListen();
          break;
        case 'think':
          voice.toThink();
          break;
        case 'speak':
          voice.toSpeak();
          break;
        case 'idle':
          voice.toIdle();
          break;
        case 'error':
          voice.toError();
          break;
      }
    } else if (e.kind === 'transcript' && e.text) {
      transcript = e.text;
    } else if (e.kind === 'reply' && e.text) {
      reply = e.text;
    } else if (e.kind === 'bargein') {
      voice.toListen();
    } else if (e.kind === 'error') {
      error = e.error ?? 'unknown error';
      voice.toError();
    }
  }

  async function pttStart() {
    if (!client || !connected) return;
    // Barge-in if Vector is mid-speech.
    if (pttDown) return;
    pttDown = true;
    transcript = '';
    reply = '';
    error = '';
    try {
      // If we were speaking, signal barge-in first so the backend
      // cancels TTS; then re-open the mic stream.
      client.bargeIn();
      await client.startCapture();
    } catch (e) {
      error = (e as Error).message;
      pttDown = false;
    }
  }

  function pttEnd() {
    if (!pttDown || !client) return;
    pttDown = false;
    client.endTurn();
  }

  onMount(loadToken);

  onDestroy(() => {
    client?.close();
  });
</script>

<svelte:head>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
</svelte:head>

<main>
  <header>
    <h1>Vector — voice</h1>
  </header>

  {#if !connected}
    <section class="connect">
      <p class="hint">
        Push-to-talk over the local backend. If <code>VECTOR_BACKEND_BEARER</code> is set,
        paste the token below; otherwise leave it blank.
      </p>
      <input
        type="password"
        placeholder="bearer token (optional)"
        bind:value={token}
        on:change={() => saveToken(token)}
      />
      <button class="primary" on:click={connect} disabled={connecting}>
        {connecting ? 'Connecting…' : 'Connect'}
      </button>
      {#if error}<p class="error">{error}</p>{/if}
    </section>
  {:else}
    <section class="stage">
      <Orb />

      <button
        class="ptt"
        class:active={pttDown}
        on:mousedown={pttStart}
        on:mouseup={pttEnd}
        on:mouseleave={pttEnd}
        on:touchstart|preventDefault={pttStart}
        on:touchend|preventDefault={pttEnd}
        on:touchcancel|preventDefault={pttEnd}
      >
        {pttDown ? 'Listening… (release to send)' : 'Hold to talk'}
      </button>

      <dl class="transcripts">
        <dt>You said</dt>
        <dd>{transcript || '—'}</dd>
        <dt>Vector</dt>
        <dd>{reply || '—'}</dd>
      </dl>

      {#if error}
        <p class="error">{error}</p>
      {/if}
    </section>
  {/if}
</main>

<style>
  main {
    max-width: 480px;
    margin: 0 auto;
    padding: 1.5rem;
    font-family: system-ui, sans-serif;
  }
  header h1 {
    margin: 0 0 1rem;
    font-size: 1.4rem;
  }
  .connect {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .hint {
    margin: 0;
    color: #6b7280;
    font-size: 0.85rem;
    line-height: 1.45;
  }
  code {
    background: #f3f4f6;
    padding: 0 0.2rem;
    border-radius: 3px;
    font-size: 0.8em;
  }
  input[type='password'] {
    height: 44px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 0 0.75rem;
    font-size: 1rem;
  }
  button {
    height: 48px;
    border-radius: 8px;
    border: none;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }
  button.primary {
    background: #111827;
    color: white;
  }
  button:disabled {
    opacity: 0.5;
    cursor: progress;
  }
  .stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }
  .ptt {
    width: 100%;
    height: 72px;
    background: #3b82f6;
    color: white;
    font-size: 1.05rem;
    touch-action: manipulation;
    user-select: none;
  }
  .ptt.active {
    background: #22c55e;
  }
  .transcripts {
    width: 100%;
    background: #f9fafb;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin: 0;
  }
  .transcripts dt {
    color: #6b7280;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.5rem;
  }
  .transcripts dt:first-child {
    margin-top: 0;
  }
  .transcripts dd {
    margin: 0.2rem 0 0;
    color: #111827;
  }
  .error {
    color: #ef4444;
    margin: 0;
  }
</style>
