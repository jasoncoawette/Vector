<script lang="ts">
  export let data: number[] = [];
  export let w: number = 200;
  export let h: number = 36;
  export let color: string = 'var(--vec)';
  export let fill: boolean = true;

  $: max = Math.max(...data);
  $: min = Math.min(...data);
  $: span = max - min || 1;
  $: pts = data.map((v, i) => [i * (w / (data.length - 1)), h - ((v - min) / span) * (h - 4) - 2]);
  $: d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
</script>

<svg width={w} height={h} style="display: block;">
  {#if fill}<path d="{d} L{w} {h} L0 {h} Z" fill={color} opacity="0.08"/>{/if}
  <path d={d} fill="none" stroke={color} stroke-width="1.25"/>
</svg>
