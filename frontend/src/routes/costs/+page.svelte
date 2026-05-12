<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Sparkline from '$lib/Sparkline.svelte';
  import { fetchCosts, type CostSummary } from '$lib/api';

  const TIER_COLOR: Record<string, string> = {
    haiku: '#22c55e',
    sonnet: '#3b82f6',
    opus: '#a855f7'
  };

  let data: CostSummary | null = null;
  let error = '';
  let loading = true;
  let timer: ReturnType<typeof setInterval> | null = null;

  $: dailyValues = (data?.daily ?? []).map((d) => d.total_usd);
  $: budgetPct = (() => {
    if (!data || !data.daily_budget_usd) return 0;
    return Math.min(1, data.today_usd / data.daily_budget_usd);
  })();

  function fmtUsd(v: number, digits = 2): string {
    return `$${v.toFixed(digits)}`;
  }

  function fmtDay(d: string): string {
    // ISO YYYY-MM-DD; show MM/DD for the dashboard.
    const parts = d.split('-');
    if (parts.length !== 3) return d;
    return `${parts[1]}/${parts[2]}`;
  }

  async function refresh() {
    try {
      data = await fetchCosts(14);
      error = '';
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    refresh();
    timer = setInterval(refresh, 10_000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<main>
  <h1>Costs</h1>
  <p class="sub">Rolling spend across agents, verifier, and routing tiers.</p>

  {#if loading}
    <p>Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if data}
    {#if data.over_budget_today}
      <div class="alert">
        <strong>Over budget</strong>: today is {fmtUsd(data.today_usd, 4)} of
        {fmtUsd(data.daily_budget_usd, 2)} cap.
      </div>
    {/if}

    <section class="topline">
      <article class="card">
        <h2>Today</h2>
        <div class="big">{fmtUsd(data.today_usd, 4)}</div>
        <div class="sub-row">
          <span>{data.today_runs} runs</span>
          {#if data.daily_budget_usd}
            <span>budget {fmtUsd(data.daily_budget_usd, 2)}</span>
          {/if}
        </div>
        {#if data.daily_budget_usd}
          <div class="bar">
            <span
              style:width="{budgetPct * 100}%"
              style:background={data.over_budget_today ? '#ef4444' : '#22c55e'}
            ></span>
          </div>
        {/if}
      </article>
      <article class="card">
        <h2>7-day</h2>
        <div class="big">{fmtUsd(data.week_usd, 2)}</div>
        <div class="sub-row">
          <span>{data.week_runs} runs</span>
        </div>
      </article>
      <article class="card">
        <h2>30-day</h2>
        <div class="big">{fmtUsd(data.month_usd, 2)}</div>
        <div class="sub-row">
          <span>{data.month_runs} runs</span>
        </div>
      </article>
    </section>

    <section>
      <h2 class="h2">Daily spend (last 14)</h2>
      {#if dailyValues.length < 2}
        <p class="empty">not enough data yet</p>
      {:else}
        <Sparkline values={dailyValues} width={640} height={64} color="#111827" />
        <div class="day-axis">
          {#each data.daily.slice(-14) as d}
            <div class="day">
              <div class="d">{fmtDay(d.day)}</div>
              <div class="v">{fmtUsd(d.total_usd, 3)}</div>
              <div class="r">{d.runs}r</div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <section>
      <h2 class="h2">By tier (last 30 days)</h2>
      {#if data.by_tier.length === 0}
        <p class="empty">no tier decisions yet</p>
      {:else}
        <table>
          <thead>
            <tr>
              <th>tier</th>
              <th class="num">decisions</th>
              <th class="num">total</th>
              <th class="num">mean / call</th>
            </tr>
          </thead>
          <tbody>
            {#each data.by_tier as t (t.tier)}
              <tr>
                <td>
                  <span class="pill" style:background={TIER_COLOR[t.tier]}>{t.tier}</span>
                </td>
                <td class="num">{t.decisions}</td>
                <td class="num">{fmtUsd(t.total_usd, 3)}</td>
                <td class="num">{fmtUsd(t.mean_usd, 5)}</td>
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
  .alert {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #991b1b;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin: 1rem 0;
  }
  .topline {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    margin: 1rem 0 1.5rem;
  }
  .card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
  }
  .card h2 {
    margin: 0;
    font-size: 0.85rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .big {
    font-size: 1.7rem;
    font-weight: 600;
    margin-top: 0.25rem;
    font-variant-numeric: tabular-nums;
  }
  .sub-row {
    display: flex;
    justify-content: space-between;
    color: #6b7280;
    font-size: 0.8rem;
    margin-top: 0.25rem;
  }
  .bar {
    margin-top: 0.5rem;
    height: 4px;
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
  .day-axis {
    display: grid;
    grid-template-columns: repeat(14, 1fr);
    gap: 0.25rem;
    margin-top: 0.5rem;
    font-size: 0.65rem;
    color: #6b7280;
  }
  .day {
    text-align: center;
  }
  .day .v {
    color: #111827;
    font-variant-numeric: tabular-nums;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  th,
  td {
    text-align: left;
    padding: 0.5rem 0.5rem;
    border-bottom: 1px solid #f3f4f6;
  }
  th {
    color: #6b7280;
    font-weight: 500;
  }
  th.num,
  td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .pill {
    color: white;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
  .error {
    color: #ef4444;
  }
  @media (max-width: 768px) {
    .topline {
      grid-template-columns: 1fr;
    }
    .day-axis {
      grid-template-columns: repeat(7, 1fr);
    }
  }
</style>
