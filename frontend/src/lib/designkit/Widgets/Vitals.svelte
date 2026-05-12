<script lang="ts">
  import Ring from '../Charts/Ring.svelte';
  import type { VitalsData } from '../api';

  export let data: VitalsData | null = null;

  const fallback = [
    { key: 'hr', pct: 68, label: '62', sub: 'HR', heading: 'RESTING', meta: '-3 vs avg', color: 'var(--vec)' },
    { key: 'hrv', pct: 82, label: '82', sub: 'HRV', heading: 'RECOVERY', meta: '+6 vs 7d', color: 'var(--vec)' },
    { key: 'strain', pct: 48, label: '48', sub: 'STRAIN', heading: 'EXERTION', meta: 'nominal', color: 'var(--warn)' },
    { key: 'sleep', pct: 94, label: '6.4h', sub: 'SLEEP', heading: 'EFFICIENCY', meta: '94%', color: 'var(--ok)' }
  ];

  $: rows = data?.metrics?.length ? data.metrics : fallback;
</script>

<div class="wrap">
  {#each rows as r}
    <div class="cell">
      <Ring pct={r.pct} size={68} label={r.label} sub={r.sub} color={r.color}/>
      <div>
        <div class="mono h">{r.heading}</div>
        <div class="mono m" style="color: {r.color};">{r.meta}</div>
      </div>
    </div>
  {/each}
</div>

<style>
  .wrap { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; height: 100%; align-content: center; }
  .cell { display: flex; align-items: center; gap: 12px; }
  .h { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; }
  .m { font-size: 11px; margin-top: 2px; }
</style>
