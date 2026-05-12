<script lang="ts">
  export let data: number[] = [];
  export let size: number = 160;
  export let color: string = 'var(--vec)';

  $: cx = size / 2;
  $: cy = size / 2;
  $: max = Math.max(...data);
</script>

<svg width={size} height={size}>
  <circle cx={cx} cy={cy} r={size / 2 - 30} stroke="rgba(255,255,255,0.06)" fill="none"/>
  {#each data as v, i}
    {@const a = (i / data.length) * Math.PI * 2 - Math.PI / 2}
    {@const r1 = size / 2 - 30}
    {@const r2 = r1 + (v / max) * 26}
    <line
      x1={cx + Math.cos(a) * r1} y1={cy + Math.sin(a) * r1}
      x2={cx + Math.cos(a) * r2} y2={cy + Math.sin(a) * r2}
      stroke={color} stroke-width="2" stroke-linecap="round" opacity={0.45 + (v / max) * 0.55}
    />
  {/each}
  <circle cx={cx} cy={cy} r="3" fill={color}/>
</svg>
