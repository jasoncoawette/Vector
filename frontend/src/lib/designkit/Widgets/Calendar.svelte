<script lang="ts">
  import type { CalendarData } from '../api';

  export let data: CalendarData | null = null;

  const fallback = [
    { t: '09:00', title: 'Standup · Platform', color: 'var(--vec)', live: false, dur: '15m' },
    { t: '10:30', title: '1:1 with Mira', color: 'var(--gold)', live: false, dur: '30m' },
    { t: '13:00', title: 'Series B demo · v7', color: 'var(--mag)', live: true, dur: '45m' },
    { t: '15:30', title: 'Deep work · pricing', color: 'var(--ok)', live: false, dur: '2h' },
    { t: '19:00', title: 'Dinner · Saburo', color: 'var(--ink-2)', live: false, dur: '-' }
  ];

  $: events = data?.events?.length ? data.events : fallback;
</script>

<div class="wrap">
  {#each events as e, i}
    <div class="row" class:last={i === events.length - 1}>
      <span class="mono time" style="color: {e.live ? 'var(--vec)' : 'var(--ink-1)'};">{e.t}</span>
      <span class="bar" style="background: {e.color};"></span>
      <span class="ttl">{e.title}</span>
      <span class="mono dur">{e.dur}</span>
    </div>
  {/each}
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .row {
    display: grid; grid-template-columns: 44px 8px 1fr auto;
    gap: 10px; align-items: center; padding: 8px 0;
    border-bottom: 1px solid var(--hair);
  }
  .row.last { border-bottom: none; }
  .time { font-size: 11px; }
  .bar { width: 3px; height: 22px; border-radius: 2px; }
  .ttl { font-size: 13px; color: var(--ink-0); }
  .dur { font-size: 10px; color: var(--ink-3); }
</style>
