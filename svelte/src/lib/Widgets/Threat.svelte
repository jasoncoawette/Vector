<script lang="ts">
  import StepLine from '../Charts/StepLine.svelte';
  import Badge from '../Primitives/Badge.svelte';

  const data = Array.from({ length: 40 }).map((_, i) =>
    0.2 + Math.sin(i * 0.4 + 1) * 0.15 + Math.random() * 0.4 + (i === 28 ? 0.5 : 0) + (i === 35 ? 0.7 : 0)
  );
</script>

<div class="wrap">
  <div class="head">
    <div>
      <div class="mono lbl">SIGNAL · LIVE</div>
      <div class="ttl">2 anomalies · last 4h</div>
    </div>
    <Badge color="var(--warn)">ELEVATED</Badge>
  </div>
  <div class="chart"><StepLine {data} threshold={0.65} w={300} h={84}/></div>
  <div class="mono foot">ANOMALIES · 21:14, 21:38 &nbsp;·&nbsp; THRESHOLD 0.65σ</div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 8px; height: 100%; }
  .head { display: flex; justify-content: space-between; align-items: baseline; }
  .lbl { font-size: 10px; color: var(--ink-3); letter-spacing: 0.22em; }
  .ttl { font-size: 18px; font-weight: 500; margin-top: 2px; }
  .chart { flex: 1; min-height: 0; display: flex; align-items: center; }
  .foot { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; }
</style>
