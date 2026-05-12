<script lang="ts">
  import type { ClockData } from '../api';

  export let data: ClockData | null = null;

  const fallback = [
    { name: 'NEW YORK', time: '21:14' },
    { name: 'LONDON', time: '02:14' },
    { name: 'TOKYO', time: '11:14' },
    { name: 'SAN FRANCISCO', time: '18:14' }
  ];

  $: zones = data?.zones?.length ? data.zones : fallback;
</script>

<div class="wrap">
  {#each zones as z, i}
    <div class="row" class:last={i === zones.length - 1}>
      <span class="mono name">{z.name}</span>
      <span class="mono time">{z.time}</span>
    </div>
  {/each}
</div>

<style>
  .wrap { display: flex; flex-direction: column; justify-content: space-between; height: 100%; }
  .row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding-bottom: 6px; border-bottom: 1px solid var(--hair);
  }
  .row.last { border-bottom: none; padding-bottom: 0; }
  .name { font-size: 10px; color: var(--ink-2); letter-spacing: 0.22em; }
  .time { font-size: 22px; font-weight: 400; color: var(--ink-0); letter-spacing: 0.04em; }
</style>
