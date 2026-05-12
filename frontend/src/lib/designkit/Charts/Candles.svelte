<script lang="ts">
  export let data: { o: number; h: number; l: number; c: number }[] = [];
  export let w: number = 320;
  export let h: number = 140;

  $: allLo = Math.min(...data.map((d) => d.l));
  $: allHi = Math.max(...data.map((d) => d.h));
  $: span = allHi - allLo || 1;
  $: cw = (w - data.length * 2) / data.length;
  $: y = (v: number) => h - ((v - allLo) / span) * (h - 8) - 4;
</script>

<svg width={w} height={h}>
  {#each data as d, i}
    {@const x = i * (cw + 2)}
    {@const up = d.c >= d.o}
    {@const col = up ? 'var(--ok)' : 'var(--crit)'}
    <g>
      <line x1={x + cw / 2} x2={x + cw / 2} y1={y(d.h)} y2={y(d.l)} stroke={col} stroke-width="1"/>
      <rect x={x} y={y(Math.max(d.o, d.c))} width={cw}
        height={Math.max(1, Math.abs(y(d.o) - y(d.c)))} fill={col} opacity="0.85"/>
    </g>
  {/each}
</svg>
