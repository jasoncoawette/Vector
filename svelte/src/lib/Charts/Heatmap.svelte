<script lang="ts">
  export let rows: number = 7;
  export let cols: number = 24;
  export let seed: number = 9;
  export let w: number = 320;
  export let h: number = 90;
  export let color: string = 'var(--vec)';

  function gen() {
    let r = seed;
    const rnd = () => { r = (r * 9301 + 49297) % 233280; return r / 233280; };
    const out: { x: number; y: number; v: number }[] = [];
    for (let y = 0; y < rows; y++)
      for (let x = 0; x < cols; x++)
        out.push({ x, y, v: Math.pow(rnd(), 1.4) });
    return out;
  }
  $: cells = gen();
  $: cw = w / cols;
  $: ch = h / rows;
</script>

<svg width={w} height={h}>
  {#each cells as c}
    <rect x={c.x * cw + 0.5} y={c.y * ch + 0.5} width={cw - 1.5} height={ch - 1.5}
      fill={color} opacity={0.05 + c.v * 0.8} rx="1"/>
  {/each}
</svg>
