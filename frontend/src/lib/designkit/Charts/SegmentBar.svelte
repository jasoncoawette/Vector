<script lang="ts">
  export let segments: { v: number; c: string }[] = [];
  export let w: number = 320;
  export let h: number = 8;

  $: total = segments.reduce((a, s) => a + s.v, 0);
  $: rendered = (() => {
    let x = 0;
    return segments.map((s) => {
      const sw = (s.v / total) * w;
      const out = { ...s, x, sw };
      x += sw;
      return out;
    });
  })();
</script>

<svg width={w} height={h}>
  {#each rendered as r}
    <rect x={r.x} y="0" width={Math.max(0, r.sw - 1)} height={h} fill={r.c} rx="1"/>
  {/each}
</svg>
