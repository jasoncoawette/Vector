<script lang="ts">
  import Heatmap from '../Charts/Heatmap.svelte';
  import type { HeatData } from '../api';

  export let data: HeatData | null = null;

  $: label = data?.label ?? 'ACTIVITY · 7×24';
  $: title = data?.title ?? 'Deep-work density';
  $: total = data?.total_hours ?? 52;
  $: scaleMin = data?.scale_min ?? 0;
  $: scaleMax = data?.scale_max ?? 8;
  $: grid = data?.grid && data.grid.length ? data.grid : null;
</script>

<div class="wrap">
  <div class="head">
    <div>
      <div class="mono lbl">{label}</div>
      <div class="ttl">{title}</div>
    </div>
    <span class="mono total">{total}h this week</span>
  </div>
  <Heatmap w={300} h={90} color="var(--vec)" {grid}/>
  <div class="row mono">
    <span>MON · TUE · WED · THU · FRI · SAT · SUN</span>
    <span>{scaleMin} → {scaleMax}h</span>
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 10px; height: 100%; }
  .head { display: flex; justify-content: space-between; align-items: baseline; }
  .lbl { font-size: 10px; color: var(--ink-3); letter-spacing: 0.22em; }
  .ttl { font-size: 18px; font-weight: 500; margin-top: 2px; }
  .total { font-size: 10px; color: var(--ink-3); }
  .row { display: flex; justify-content: space-between; font-size: 9px; color: var(--ink-3); letter-spacing: 0.16em; }
</style>
