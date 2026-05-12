<script lang="ts">
  import { onMount } from 'svelte';
  import Sparkline from '$lib/Sparkline.svelte';
  import { fetchMission, type MissionResponse } from '$lib/api';

  const SERIES_META: Record<string, { label: string; color: string }> = {
    us_compute_share: { label: 'US AI compute share', color: '#3b82f6' },
    china_compute_output: { label: 'China AI compute output', color: '#ef4444' },
    stratus_share_us_mil: { label: 'Stratus share of US mil compute', color: '#22c55e' }
  };

  let data: MissionResponse | null = null;
  let error = '';
  let loading = true;

  function pct(v: number): string {
    return `${(v * 100).toFixed(1)}%`;
  }

  onMount(async () => {
    try {
      data = await fetchMission();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  });
</script>

<main>
  <h1>Mission</h1>
  <p class="sub">US vs China compute — week {data?.week ?? '…'}</p>

  {#if loading}
    <p>Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if data}
    <section>
      <h2>Compute trends</h2>
      <ul class="series">
        {#each Object.keys(SERIES_META) as key}
          {@const points = data.series[key] ?? []}
          {@const meta = SERIES_META[key]}
          {@const last = points.length > 0 ? points[points.length - 1].value : null}
          <li>
            <div class="row">
              <span class="dot" style:background={meta.color}></span>
              <span class="label">{meta.label}</span>
              <span class="value">{last === null ? '—' : pct(last)}</span>
            </div>
            <Sparkline values={points.map((p) => p.value)} color={meta.color} />
          </li>
        {/each}
      </ul>
    </section>

    <section>
      <h2>Top US choke points</h2>
      {#if data.choke_points.length === 0}
        <p class="empty">none logged for this week yet</p>
      {:else}
        <ol class="choke">
          {#each data.choke_points as p}
            <li>
              <strong>{p.title}</strong>
              {#if p.note}<div class="note">{p.note}</div>{/if}
            </li>
          {/each}
        </ol>
      {/if}
    </section>
  {/if}
</main>

<style>
  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  .sub {
    color: #6b7280;
    margin-top: -0.5rem;
  }
  section {
    margin-bottom: 2rem;
  }
  ul.series {
    list-style: none;
    padding: 0;
  }
  ul.series li {
    padding: 0.75rem 0;
    border-bottom: 1px solid #eee;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .label {
    flex: 1;
  }
  .value {
    font-family: ui-monospace, monospace;
    font-weight: 600;
  }
  ol.choke {
    padding-left: 1.25rem;
  }
  ol.choke li {
    padding: 0.4rem 0;
  }
  .note {
    color: #6b7280;
    font-size: 0.85rem;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
  .error {
    color: #ef4444;
  }
</style>
