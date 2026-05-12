<script lang="ts">
  import Heatmap from '../Charts/Heatmap.svelte';
</script>

<div class="wrap">
  <div class="head">
    <div>
      <div class="mono lbl">ACTIVITY · 7×24</div>
      <div class="ttl">Deep-work density</div>
    </div>
    <span class="mono total">52h this week</span>
  </div>
  <Heatmap w={300} h={90} color="var(--vec)"/>
  <div class="row mono">
    <span>MON · TUE · WED · THU · FRI · SAT · SUN</span>
    <span>0 → 8h</span>
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
