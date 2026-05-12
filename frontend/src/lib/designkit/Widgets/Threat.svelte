<script lang="ts">
  import StepLine from '../Charts/StepLine.svelte';
  import Badge from '../Primitives/Badge.svelte';
  import type { ThreatData } from '../api';

  export let data: ThreatData | null = null;

  const fallbackSeries = Array.from({ length: 40 }).map((_, i) =>
    0.2 + Math.sin(i * 0.4 + 1) * 0.15 + Math.random() * 0.4 + (i === 28 ? 0.5 : 0) + (i === 35 ? 0.7 : 0)
  );

  $: series = data?.series?.length ? data.series : fallbackSeries;
  $: label = data?.label ?? 'SIGNAL · LIVE';
  $: title = data?.title ?? '2 anomalies · last 4h';
  $: severity = data?.severity ?? 'ELEVATED';
  $: threshold = data?.threshold ?? 0.65;
  $: anomalies = data?.anomalies_at ?? ['21:14', '21:38'];
  $: badgeColor =
    severity === 'CRITICAL' ? 'var(--crit)' :
    severity === 'ELEVATED' ? 'var(--warn)' : 'var(--ok)';
</script>

<div class="wrap">
  <div class="head">
    <div>
      <div class="mono lbl">{label}</div>
      <div class="ttl">{title}</div>
    </div>
    <Badge color={badgeColor}>{severity}</Badge>
  </div>
  <div class="chart"><StepLine data={series} {threshold} w={300} h={84}/></div>
  <div class="mono foot">ANOMALIES · {anomalies.join(', ')} &nbsp;·&nbsp; THRESHOLD {threshold}σ</div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 8px; height: 100%; }
  .head { display: flex; justify-content: space-between; align-items: baseline; }
  .lbl { font-size: 10px; color: var(--ink-3); letter-spacing: 0.22em; }
  .ttl { font-size: 18px; font-weight: 500; margin-top: 2px; }
  .chart { flex: 1; min-height: 0; display: flex; align-items: center; }
  .foot { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; }
</style>
