<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Sparkline from '$lib/Sparkline.svelte';
  import {
    fetchRoutingLog,
    fetchRoutingStats,
    type RoutingLogEntry,
    type RoutingStats,
    type RoutingTier
  } from '$lib/api';

  const TIER_COLOR: Record<string, string> = {
    haiku: '#22c55e',
    sonnet: '#3b82f6',
    opus: '#a855f7'
  };

  const TIER_PRICE_HINT: Record<string, string> = {
    haiku: '~$1 / Mtok in',
    sonnet: '~$3 / Mtok in',
    opus: '~$15 / Mtok in'
  };

  let stats: RoutingStats | null = null;
  let entries: RoutingLogEntry[] = [];
  let error = '';
  let loading = true;
  let timer: ReturnType<typeof setInterval> | null = null;

  $: tiers = stats?.tiers ?? [];
  $: totalDecisions = tiers.reduce((acc, t) => acc + t.decisions, 0);
  $: totalCostFromMeans = tiers.reduce(
    (acc, t) => acc + t.mean_cost_usd * (t.successes + t.failures),
    0
  );
  $: sparkValues = (() => {
    // Cost-per-decision over time using the log tail, oldest first.
    if (entries.length === 0) return [];
    return entries
      .slice()
      .reverse()
      .map((e) => Number(e.cost_usd ?? 0));
  })();

  function tierShare(t: RoutingTier): number {
    return totalDecisions === 0 ? 0 : t.decisions / totalDecisions;
  }

  function fmtTime(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString();
  }

  function fmtCost(v: number | null): string {
    if (v === null || v === undefined) return '—';
    return `$${v.toFixed(4)}`;
  }

  function fmtOutcome(e: RoutingLogEntry): string {
    if (e.outcome === null) return '·';
    return e.outcome === 1 ? '✓' : '✗';
  }

  async function refresh() {
    try {
      const [s, l] = await Promise.all([fetchRoutingStats(), fetchRoutingLog(120)]);
      stats = s;
      entries = l;
      error = '';
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    refresh();
    timer = setInterval(refresh, 4000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<main>
  <h1>Routing</h1>
  <p class="sub">Live tier mix, learned priors, and recent decisions.</p>

  {#if loading}
    <p>Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else}
    <section class="cards">
      {#each tiers as t (t.tier)}
        <article class="card">
          <header>
            <span class="dot" style:background={TIER_COLOR[t.tier]}></span>
            <h2>{t.tier.toUpperCase()}</h2>
            <span class="hint">{TIER_PRICE_HINT[t.tier]}</span>
          </header>
          <div class="row">
            <span class="k">decisions</span>
            <span class="v">{t.decisions}</span>
          </div>
          <div class="row">
            <span class="k">share</span>
            <span class="v">{(tierShare(t) * 100).toFixed(1)}%</span>
          </div>
          <div class="row">
            <span class="k">mean cost</span>
            <span class="v">${t.mean_cost_usd.toFixed(4)}</span>
          </div>
          <div class="row">
            <span class="k">success rate</span>
            <span class="v">{(t.success_rate * 100).toFixed(0)}%</span>
          </div>
          <div class="row">
            <span class="k">priors</span>
            <span class="v small">α={t.alpha.toFixed(1)} β={t.beta.toFixed(1)}</span>
          </div>
          <div class="row">
            <span class="k">trials</span>
            <span class="v">{t.trials}</span>
          </div>
          <div class="bar">
            <span style:width="{tierShare(t) * 100}%" style:background={TIER_COLOR[t.tier]}></span>
          </div>
        </article>
      {/each}
    </section>

    <section>
      <h2 class="h2">Cost per decision (recent)</h2>
      {#if sparkValues.length < 2}
        <p class="empty">not enough data yet</p>
      {:else}
        <Sparkline values={sparkValues} width={640} height={64} color="#111827" />
      {/if}
    </section>

    <section>
      <h2 class="h2">Recent decisions</h2>
      {#if entries.length === 0}
        <p class="empty">no decisions logged yet</p>
      {:else}
        <table>
          <thead>
            <tr>
              <th>time</th>
              <th>type</th>
              <th>tier</th>
              <th>model</th>
              <th class="num">score</th>
              <th>src</th>
              <th>ok</th>
              <th class="num">cost</th>
            </tr>
          </thead>
          <tbody>
            {#each entries as e, i (i)}
              <tr>
                <td>{fmtTime(e.ts)}</td>
                <td>{e.agent_type ?? '—'}</td>
                <td>
                  <span class="pill" style:background={TIER_COLOR[e.tier]}>{e.tier}</span>
                </td>
                <td class="model">{e.model}</td>
                <td class="num">{e.score.toFixed(2)}</td>
                <td class="src">{e.source}</td>
                <td class="ok" class:fail={e.outcome === 0}>{fmtOutcome(e)}</td>
                <td class="num">{fmtCost(e.cost_usd)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>
  {/if}
</main>

<style>
  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  .sub {
    color: #6b7280;
    margin-top: -0.5rem;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
  }
  .card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
  }
  .card header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
  }
  .card h2 {
    margin: 0;
    font-size: 0.95rem;
    letter-spacing: 0.05em;
  }
  .hint {
    margin-left: auto;
    font-size: 0.7rem;
    color: #9ca3af;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  .row {
    display: flex;
    justify-content: space-between;
    padding: 0.2rem 0;
    font-size: 0.85rem;
  }
  .k {
    color: #6b7280;
  }
  .v {
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }
  .v.small {
    font-family: ui-monospace, monospace;
    font-size: 0.75rem;
  }
  .bar {
    height: 4px;
    margin-top: 0.5rem;
    background: #f3f4f6;
    border-radius: 2px;
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
  }
  .h2 {
    margin: 1.5rem 0 0.5rem;
    font-size: 0.9rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  th,
  td {
    text-align: left;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #f3f4f6;
  }
  th {
    color: #6b7280;
    font-weight: 500;
  }
  td.num,
  th.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  td.model {
    font-family: ui-monospace, monospace;
    font-size: 0.75rem;
    color: #4b5563;
  }
  td.src {
    color: #6b7280;
    font-size: 0.75rem;
  }
  .pill {
    color: white;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  td.ok {
    color: #22c55e;
    text-align: center;
    font-weight: 600;
  }
  td.ok.fail {
    color: #ef4444;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
  .error {
    color: #ef4444;
  }
  @media (max-width: 768px) {
    .cards {
      grid-template-columns: 1fr;
    }
  }
</style>
