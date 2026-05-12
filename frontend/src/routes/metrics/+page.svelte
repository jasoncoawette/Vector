<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchMetrics, type MetricPoint } from '$lib/api';

  const SECTION_ORDER = ['stratus', 'build', 'network', 'personal', 'mission'];
  const SECTION_LABELS: Record<string, string> = {
    stratus: 'Stratus Top Line',
    build: 'Build',
    network: 'Network',
    personal: 'Personal',
    mission: 'Mission (US vs China)'
  };

  let sections: Record<string, MetricPoint[]> = {};
  let error = '';
  let loading = true;

  function format(p: MetricPoint): string {
    if (p.unit === 'usd') return `$${p.value.toLocaleString()}`;
    if (p.unit === 'pct') return `${(p.value * 100).toFixed(1)}%`;
    return `${p.value}${p.unit ? ' ' + p.unit : ''}`;
  }

  onMount(async () => {
    try {
      const r = await fetchMetrics();
      sections = r.sections;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  });
</script>

<main>
  <h1>Metrics</h1>
  {#if loading}
    <p>Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else}
    {#each SECTION_ORDER as section}
      <section>
        <h2>{SECTION_LABELS[section]}</h2>
        {#if !sections[section] || sections[section].length === 0}
          <p class="empty">no data yet</p>
        {:else}
          <ul>
            {#each sections[section] as p}
              <li class:stale={p.stale}>
                <span class="name">{p.name}</span>
                <span class="value">{format(p)}</span>
                {#if p.stale}<span class="badge">stale</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/each}
  {/if}
</main>

<style>
  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  section {
    margin-bottom: 1.5rem;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  li {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid #eee;
  }
  li.stale {
    opacity: 0.6;
  }
  .badge {
    background: #fef3c7;
    color: #92400e;
    padding: 0 0.4rem;
    border-radius: 4px;
    font-size: 0.75rem;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
  .error {
    color: #ef4444;
  }
  .name {
    font-weight: 500;
  }
</style>
