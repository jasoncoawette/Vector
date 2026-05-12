<script lang="ts">
  export let data: number[] = [];
  export let w: number = 320;
  export let h: number = 120;
  export let color: string = 'var(--vec)';

  const gid = 'g' + Math.random().toString(36).slice(2, 7);
  $: max = Math.max(...data);
  $: min = Math.min(...data);
  $: span = max - min || 1;
  $: pts = data.map((v, i) => [i * (w / (data.length - 1)), h - ((v - min) / span) * (h - 10) - 5]);
  $: d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
</script>

<svg width={w} height={h}>
  <defs>
    <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color={color} stop-opacity="0.32"/>
      <stop offset="100%" stop-color={color} stop-opacity="0"/>
    </linearGradient>
  </defs>
  {#each [0.25, 0.5, 0.75] as y}
    <line x1="0" x2={w} y1={h * y} y2={h * y} stroke="rgba(255,255,255,0.05)"/>
  {/each}
  <path d="{d} L{w} {h} L0 {h} Z" fill="url(#{gid})"/>
  <path d={d} fill="none" stroke={color} stroke-width="1.4"/>
</svg>
