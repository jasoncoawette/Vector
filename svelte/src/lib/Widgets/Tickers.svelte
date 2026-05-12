<script lang="ts">
  import Sparkline from '../Charts/Sparkline.svelte';
  const list = [
    { sym: 'SPX',  px: '5,872.4', ch: +0.42, spark: [12, 14, 16, 15, 18, 17, 19, 22, 21, 24, 23, 26] },
    { sym: 'NDX',  px: '20,114',  ch: +0.81, spark: [22, 20, 24, 26, 25, 28, 27, 30, 32, 31, 34, 38] },
    { sym: 'BTC',  px: '95,214',  ch: -1.24, spark: [28, 30, 29, 27, 26, 28, 24, 22, 23, 21, 19, 20] },
    { sym: 'ETH',  px: '3,284',   ch: +0.18, spark: [12, 13, 12, 14, 15, 14, 16, 15, 17, 16, 18, 17] },
    { sym: 'VEC',  px: '142.86',  ch: +2.41, spark: [8, 10, 12, 11, 14, 17, 16, 19, 22, 24, 28, 30] },
    { sym: 'DXY',  px: '104.21',  ch: -0.12, spark: [20, 21, 21, 20, 19, 20, 19, 18, 19, 18, 17, 18] }
  ];
</script>

<div class="wrap">
  {#each list as t, i}
    <div class="row" class:last={i === list.length - 1}>
      <span class="sym mono">{t.sym}</span>
      <Sparkline data={t.spark} w={120} h={22} color={t.ch >= 0 ? 'var(--ok)' : 'var(--crit)'} fill={false}/>
      <span class="px mono">{t.px}</span>
      <span class="ch mono" style="color: {t.ch >= 0 ? 'var(--ok)' : 'var(--crit)'};">
        {t.ch >= 0 ? '+' : ''}{t.ch.toFixed(2)}%
      </span>
    </div>
  {/each}
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: 100%; }
  .row {
    display: grid; grid-template-columns: 44px 1fr 70px 60px;
    align-items: center; gap: 8px; padding: 6px 0;
    border-bottom: 1px solid var(--hair);
  }
  .row.last { border-bottom: none; }
  .sym { font-size: 11px; color: var(--ink-0); font-weight: 500; }
  .px { font-size: 11px; color: var(--ink-1); text-align: right; }
  .ch { font-size: 10px; text-align: right; }
</style>
