<script lang="ts">
  const zones: [string, string][] = [
    ['NEW YORK', '21:14'],
    ['LONDON', '02:14'],
    ['TOKYO', '11:14'],
    ['SAN FRANCISCO', '18:14']
  ];
</script>

<div class="wrap">
  {#each zones as [n, t], i}
    <div class="row" class:last={i === zones.length - 1}>
      <span class="mono name">{n}</span>
      <span class="mono time">{t}</span>
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
