<script lang="ts">
  import type { NewsData } from '../api';

  export let data: NewsData | null = null;

  const fallback = [
    { src: 'REUTERS', headline: 'Fed signals pause on rate cuts pending CPI', age: '4m', tag: 'MARKETS' },
    { src: 'BLOOMBERG', headline: 'Nvidia ships Blackwell ahead of schedule', age: '22m', tag: 'TECH' },
    { src: 'AP', headline: 'Senate advances AI safety reporting bill', age: '1h', tag: 'POLICY' },
    { src: 'FT', headline: 'Container freight rates fall 8% week-over-week', age: '3h', tag: 'GLOBAL' }
  ];

  $: items = data?.items?.length ? data.items : fallback;
</script>

<div class="feed">
  {#each items as n, i (i)}
    <div class="row" class:last={i === items.length - 1}>
      <span class="src mono">{n.src}</span>
      <div>
        <div class="hl">{n.headline}</div>
        <div class="meta mono">{n.tag} · {n.age}</div>
      </div>
    </div>
  {/each}
</div>

<style>
  .feed { display: flex; flex-direction: column; gap: 8px; height: 100%; overflow: hidden; }
  .row {
    display: grid; grid-template-columns: 72px 1fr; gap: 10px;
    padding-bottom: 8px; border-bottom: 1px solid var(--hair);
  }
  .row.last { border-bottom: none; padding-bottom: 0; }
  .src { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; margin-top: 3px; }
  .hl { font-size: 12.5px; color: var(--ink-0); line-height: 1.4; }
  .meta { font-size: 9px; color: var(--ink-3); margin-top: 3px; letter-spacing: 0.16em; }
</style>
