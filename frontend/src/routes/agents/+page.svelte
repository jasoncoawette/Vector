<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    killAgent,
    listAgents,
    spawnAgent,
    type AgentRun,
    type AgentType
  } from '$lib/api';

  let runs: AgentRun[] = [];
  let error = '';
  let timer: ReturnType<typeof setInterval> | null = null;

  let newType: AgentType = 'research';
  let newPrompt = '';

  const STATUS_COLOR: Record<string, string> = {
    queued: '#9ca3af',
    running: '#3b82f6',
    done: '#22c55e',
    failed: '#ef4444',
    killed: '#f59e0b',
    needs_confirm: '#a855f7'
  };

  async function refresh() {
    try {
      runs = await listAgents();
      error = '';
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function spawn() {
    if (!newPrompt.trim()) return;
    try {
      await spawnAgent({ type: newType, prompt: newPrompt });
      newPrompt = '';
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function kill(id: string) {
    try {
      await killAgent(id);
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  onMount(() => {
    refresh();
    timer = setInterval(refresh, 2000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<main>
  <h1>Agents</h1>

  <form on:submit|preventDefault={spawn} class="spawn">
    <select bind:value={newType}>
      <option value="research">research</option>
      <option value="code">code</option>
      <option value="writer">writer</option>
    </select>
    <input bind:value={newPrompt} placeholder="prompt" />
    <button type="submit" disabled={!newPrompt.trim()}>Spawn</button>
  </form>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if runs.length === 0}
    <p class="empty">no agents running</p>
  {:else}
    <ul>
      {#each runs as r (r.id)}
        <li>
          <div class="row">
            <span
              class="dot"
              style:background={STATUS_COLOR[r.status] ?? '#9ca3af'}
              title={r.status}
            ></span>
            <span class="type">{r.type}</span>
            <span class="prompt">{r.prompt}</span>
            <span class="elapsed">{r.elapsed_s.toFixed(1)}s</span>
            <span class="cost">${r.cost_usd.toFixed(3)}</span>
            {#if r.long_running}
              <span class="badge">long</span>
            {/if}
            {#if r.fallback_used}
              <span class="badge">fallback</span>
            {/if}
            {#if r.status === 'running' || r.status === 'queued'}
              <button on:click={() => kill(r.id)}>kill</button>
            {/if}
          </div>
          {#if r.output}
            <pre class="output">{r.output}</pre>
          {/if}
          {#if r.error}
            <p class="error-line">{r.error}</p>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</main>

<style>
  main {
    max-width: 760px;
    margin: 0 auto;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  .spawn {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }
  .spawn input {
    flex: 1;
  }
  ul {
    list-style: none;
    padding: 0;
  }
  li {
    border-bottom: 1px solid #eee;
    padding: 0.75rem 0;
  }
  .row {
    display: flex;
    gap: 0.6rem;
    align-items: center;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  .type {
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.7rem;
  }
  .prompt {
    flex: 1;
  }
  .elapsed,
  .cost {
    font-family: ui-monospace, monospace;
    color: #6b7280;
    font-size: 0.85rem;
  }
  .badge {
    background: #fef3c7;
    color: #92400e;
    padding: 0 0.4rem;
    border-radius: 4px;
    font-size: 0.7rem;
  }
  .output {
    margin: 0.4rem 0 0 1.5rem;
    background: #f9fafb;
    padding: 0.5rem;
    border-radius: 4px;
    white-space: pre-wrap;
    font-size: 0.85rem;
  }
  .error,
  .error-line {
    color: #ef4444;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
</style>
