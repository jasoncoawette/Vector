<script lang="ts">
  export let w: number = 220;
  export let h: number = 32;
  export let color: string = 'var(--vec)';
  export let bars: number = 48;

  $: arr = Array.from({ length: bars }).map((_, i) =>
    (Math.sin(i * 0.6) * 0.5 + 0.5) * (0.4 + Math.random() * 0.6)
  );
</script>

<svg width={w} height={h}>
  {#each arr as v, i}
    {@const bh = v * h}
    <rect x={i * (w / bars)} y={(h - bh) / 2} width={w / bars - 1} height={bh}
      fill={color} opacity={0.3 + v * 0.7} rx="0.6"/>
  {/each}
</svg>
