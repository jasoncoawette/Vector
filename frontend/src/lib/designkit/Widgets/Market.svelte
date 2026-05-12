<script lang="ts">
  import Candles from '../Charts/Candles.svelte';
  import type { MarketData } from '../api';

  export let data: MarketData | null = null;

  function genCandles() {
    const a: { o: number; h: number; l: number; c: number }[] = [];
    for (let i = 0; i < 22; i++) {
      const base = 100 + i * 1.4 + Math.sin(i * 0.6) * 5;
      const o = base + (Math.random() - 0.5) * 1.5;
      const c = o + (Math.random() - 0.45) * 3.5;
      const h = Math.max(o, c) + Math.random() * 1.6;
      const l = Math.min(o, c) - Math.random() * 1.6;
      a.push({ o, h, l, c });
    }
    return a;
  }

  $: candles = data?.candles?.length ? data.candles : genCandles();
  $: symbol = data?.symbol ?? 'NVDA';
  $: exchange = data?.exchange ?? 'NASDAQ';
  $: price = data?.price ?? 1142.08;
  $: deltaAbs = data?.delta_abs ?? 18.42;
  $: deltaPct = data?.delta_pct ?? 1.64;
  $: ranges = data?.ranges ?? ['1D', '1W', '1M', '1Y'];
  $: activeRange = data?.active_range ?? '1M';
  $: stats = data?.stats ?? { open: 1124.10, high: 1148.92, vol: '38.4M', pe: 62.1 };
  $: deltaColor = deltaAbs >= 0 ? 'var(--ok)' : 'var(--crit)';
  $: deltaSign = deltaAbs >= 0 ? '+' : '';
</script>

<div class="wrap">
  <div class="head">
    <div>
      <div class="mono lbl">{symbol} · {exchange}</div>
      <div class="px">${price.toLocaleString()}</div>
      <div class="mono delta" style="color: {deltaColor};">
        {deltaSign}{deltaAbs.toFixed(2)} · {deltaSign}{deltaPct.toFixed(2)}%
      </div>
    </div>
    <div class="ranges">
      {#each ranges as t}
        <span class="r mono" class:active={t === activeRange}>{t}</span>
      {/each}
    </div>
  </div>
  <div class="chart"><Candles data={candles} w={300} h={120}/></div>
  <div class="stats mono">
    <div><span class="k">OPEN</span>{stats.open}</div>
    <div><span class="k">HIGH</span>{stats.high}</div>
    <div><span class="k">VOL</span>{stats.vol}</div>
    <div><span class="k">P/E</span>{stats.pe}</div>
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 8px; height: 100%; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; }
  .lbl { font-size: 10px; color: var(--ink-3); letter-spacing: 0.22em; }
  .px { font-size: 28px; font-weight: 500; letter-spacing: -0.02em; margin-top: 2px; }
  .delta { font-size: 11px; }
  .ranges { display: flex; gap: 4px; }
  .r {
    font-size: 10px; padding: 3px 8px; border-radius: 4px;
    color: var(--ink-3); letter-spacing: 0.12em;
  }
  .r.active {
    background: var(--bg-3); color: var(--ink-0); border: 1px solid var(--line);
  }
  .chart { flex: 1; min-height: 0; }
  .stats { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; font-size: 10px; }
  .k { color: var(--ink-3); display: block; }
</style>
