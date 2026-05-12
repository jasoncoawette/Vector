<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    cacheLoad,
    cacheSave,
    fetchAudit,
    fetchBrief,
    fetchMetrics,
    isCacheStale,
    isLocalBackend,
    listAgents,
    spawnAgent,
    type AgentRun,
    type AuditEntry,
    type MetricPoint
  } from '$lib/api';

  let brief = '';
  let agents: AgentRun[] = [];
  let stratus: MetricPoint[] = [];
  let auditTail: AuditEntry[] = [];

  let cacheAgeMs = 0;
  let online = true;
  let error = '';
  let ptt: 'idle' | 'listen' = 'idle';
  let timer: ReturnType<typeof setInterval> | null = null;

  let newPrompt = '';

  $: stale = !online && isCacheStale(cacheAgeMs);
  $: canAct = online && isLocalBackend();

  async function refresh() {
    try {
      const [b, a, m, l] = await Promise.all([
        fetchBrief(),
        listAgents(),
        fetchMetrics(),
        fetchAudit(20)
      ]);
      brief = b.text;
      agents = a.slice(0, 5);
      stratus = m.sections.stratus ?? [];
      auditTail = l;
      online = true;
      error = '';
      cacheSave('mobile', { brief, agents, stratus, auditTail });
      cacheAgeMs = 0;
    } catch (e) {
      online = false;
      error = (e as Error).message;
      const c = cacheLoad<{
        brief: string;
        agents: AgentRun[];
        stratus: MetricPoint[];
        auditTail: AuditEntry[];
      }>('mobile');
      if (c) {
        brief = c.value.brief;
        agents = c.value.agents;
        stratus = c.value.stratus;
        auditTail = c.value.auditTail;
        cacheAgeMs = c.ageMs;
      }
    }
  }

  async function spawn() {
    if (!newPrompt.trim() || !canAct) return;
    try {
      await spawnAgent({ type: 'research', prompt: newPrompt });
      newPrompt = '';
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function pttDown() {
    if (!canAct) return;
    ptt = 'listen';
  }

  function pttUp() {
    ptt = 'idle';
  }

  onMount(() => {
    refresh();
    timer = setInterval(refresh, 4000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<svelte:head>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
</svelte:head>

<main>
  <header>
    <h1>Vector</h1>
    {#if !online}
      <span class="badge stale" class:hidden={!stale}>stale</span>
      <span class="badge offline" class:hidden={stale}>cached</span>
    {/if}
  </header>

  <button
    class="ptt"
    class:listening={ptt === 'listen'}
    on:touchstart|preventDefault={pttDown}
    on:touchend|preventDefault={pttUp}
    on:mousedown={pttDown}
    on:mouseup={pttUp}
    on:mouseleave={pttUp}
    disabled={!canAct}
  >
    {ptt === 'listen' ? 'Listening…' : 'Push to talk'}
  </button>

  <section>
    <h2>Brief</h2>
    <p class="brief">{brief || '—'}</p>
  </section>

  <section>
    <h2>Stratus</h2>
    {#if stratus.length === 0}
      <p class="empty">no metrics</p>
    {:else}
      <ul class="metrics">
        {#each stratus as p}
          <li><span>{p.name}</span><span>{p.value}{p.unit ? ' ' + p.unit : ''}</span></li>
        {/each}
      </ul>
    {/if}
  </section>

  <section>
    <h2>Agents</h2>
    {#if canAct && !stale}
      <form on:submit|preventDefault={spawn} class="spawn">
        <input bind:value={newPrompt} placeholder="research prompt" inputmode="text" />
        <button type="submit" disabled={!newPrompt.trim()}>Spawn</button>
      </form>
    {/if}
    {#if agents.length === 0}
      <p class="empty">no agents</p>
    {:else}
      <ul class="agents">
        {#each agents as a (a.id)}
          <li>
            <div class="row">
              <span class="t">{a.type}</span>
              <span class="prompt">{a.prompt}</span>
              <span class="s status-{a.status}">{a.status}</span>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section>
    <h2>Recent audit</h2>
    {#if auditTail.length === 0}
      <p class="empty">no entries</p>
    {:else}
      <ul class="audit">
        {#each auditTail.slice(0, 10) as e}
          <li class:fail={!e.ok}>
            <span class="t">{e.tool}</span>
            <span class="ok">{e.ok ? '✓' : '✗'}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if error && online}
    <p class="error">{error}</p>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
  }
  main {
    max-width: 480px;
    margin: 0 auto;
    padding: 1rem;
    font-family: system-ui, sans-serif;
    background: #fff;
    min-height: 100vh;
  }
  header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  h1 {
    flex: 1;
    margin: 0;
    font-size: 1.5rem;
  }
  h2 {
    margin: 1.2rem 0 0.5rem;
    font-size: 1rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .badge {
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
  }
  .badge.offline {
    background: #fef3c7;
    color: #92400e;
  }
  .badge.stale {
    background: #fee2e2;
    color: #991b1b;
  }
  .hidden {
    display: none;
  }
  .ptt {
    width: 100%;
    height: 64px;
    border-radius: 12px;
    border: none;
    background: #3b82f6;
    color: white;
    font-size: 1.1rem;
    font-weight: 600;
    margin: 1rem 0;
    touch-action: manipulation;
  }
  .ptt.listening {
    background: #22c55e;
  }
  .ptt:disabled {
    background: #9ca3af;
  }
  .brief {
    margin: 0;
    padding: 0.75rem;
    background: #f9fafb;
    border-radius: 8px;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  ul.metrics li,
  ul.agents li,
  ul.audit li {
    display: flex;
    gap: 0.5rem;
    padding: 0.6rem 0;
    min-height: 44px;
    align-items: center;
    border-bottom: 1px solid #f3f4f6;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    width: 100%;
  }
  .t {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #6b7280;
  }
  .prompt {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .s {
    font-size: 0.75rem;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
  }
  .status-done {
    background: #dcfce7;
    color: #166534;
  }
  .status-running {
    background: #dbeafe;
    color: #1e3a8a;
  }
  .status-failed,
  .status-killed {
    background: #fee2e2;
    color: #991b1b;
  }
  .status-needs_confirm {
    background: #f3e8ff;
    color: #6b21a8;
  }
  .spawn {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  .spawn input {
    flex: 1;
    height: 44px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 0 0.75rem;
    font-size: 1rem;
  }
  .spawn button {
    height: 44px;
    min-width: 80px;
    border-radius: 8px;
    border: none;
    background: #111827;
    color: white;
    font-weight: 600;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
    margin: 0.5rem 0;
  }
  .error {
    color: #ef4444;
  }
  .ok {
    color: #6b7280;
  }
  li.fail .ok {
    color: #ef4444;
  }
</style>
