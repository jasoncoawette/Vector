<script lang="ts">
  const items = [
    { src: 'REUTERS', t: 'Fed signals pause on rate cuts pending CPI', time: '4m', tag: 'MARKETS' },
    { src: 'BLOOMBERG', t: 'Nvidia ships Blackwell ahead of schedule', time: '22m', tag: 'TECH' },
    { src: 'AP', t: 'Senate advances AI safety reporting bill', time: '1h', tag: 'POLICY' },
    { src: 'FT', t: 'Container freight rates fall 8% week-over-week', time: '3h', tag: 'GLOBAL' }
  ];
</script>

<div class="feed">
  {#each items as n, i (i)}
    <div class="row" class:last={i === items.length - 1}>
      <span class="src mono">{n.src}</span>
      <div>
        <div class="hl">{n.t}</div>
        <div class="meta mono">{n.tag} · {n.time}</div>
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
