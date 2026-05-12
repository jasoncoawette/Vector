<script lang="ts">
  import Orb from '$lib/Orb.svelte';
  import { voice } from '$lib/voiceState';
  import { fetchGreeting } from '$lib/api';

  let greeting = '';
  let error = '';

  async function sayGreeting() {
    error = '';
    voice.toListen();
    voice.toThink();
    try {
      const r = await fetchGreeting();
      greeting = r.text;
      voice.toSpeak();
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(r.text);
        u.onend = () => voice.toIdle();
        window.speechSynthesis.speak(u);
      } else {
        setTimeout(() => voice.toIdle(), 400);
      }
    } catch (e) {
      error = (e as Error).message;
      voice.toError();
    }
  }
</script>

<main>
  <h1>Vector</h1>
  <p>Your path to the win.</p>
  <Orb />
  <div class="controls">
    <button on:click={sayGreeting}>Say greeting</button>
    <button on:click={() => voice.toIdle()}>Reset</button>
  </div>
  {#if greeting}
    <p class="line">{greeting}</p>
  {/if}
  {#if error}
    <p class="error">{error}</p>
  {/if}
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  .controls {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  .line {
    margin-top: 1rem;
    font-style: italic;
  }
  .error {
    color: #ef4444;
  }
</style>
