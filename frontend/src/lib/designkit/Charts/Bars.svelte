<script lang="ts">
  export let data: number[] = [];
  export let w: number = 220;
  export let h: number = 56;
  export let color: string = 'var(--vec)';

  $: max = Math.max(...data);
  $: bw = (w - data.length * 2) / data.length;
</script>

<svg width={w} height={h}>
  {#each data as v, i}
    <rect x={i * (bw + 2)} y={h - (v / max) * h} width={bw} height={(v / max) * h}
      fill={color} opacity={0.35 + (v / max) * 0.6} rx="1"/>
  {/each}
</svg>
