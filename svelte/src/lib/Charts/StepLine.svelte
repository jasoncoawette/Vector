<script lang="ts">
  export let data: number[] = [];
  export let threshold: number = 0.6;
  export let w: number = 320;
  export let h: number = 90;
  export let color: string = 'var(--vec)';

  $: sw = w / data.length;
  $: path = (() => {
    let p = '';
    data.forEach((v, i) => {
      const x1 = i * sw, x2 = (i + 1) * sw, y = h - v * h * 0.9 - 5;
      p += (i ? ` L${x1} ${y}` : `M${x1} ${y}`) + ` L${x2} ${y}`;
    });
    return p;
  })();
  $: ty = h - threshold * h * 0.9 - 5;
</script>

<svg width={w} height={h}>
  <line x1="0" x2={w} y1={ty} y2={ty} stroke="var(--warn)" stroke-width="1" stroke-dasharray="2 3" opacity="0.7"/>
  <path d={path} fill="none" stroke={color} stroke-width="1.4"/>
  {#each data as v, i}
    {#if v > threshold}
      <circle cx={i * sw + sw / 2} cy={h - v * h * 0.9 - 5} r="2" fill="var(--warn)"/>
    {/if}
  {/each}
</svg>
