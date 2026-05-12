<script lang="ts">
  export let slices: { v: number; color: string }[] = [];
  export let size: number = 120;
  export let thickness: number = 12;
  export let label: string = '';
  export let sub: string = '';

  $: r = size / 2 - thickness / 2 - 2;
  $: c = 2 * Math.PI * r;
  $: total = slices.reduce((s, x) => s + x.v, 0);
  $: rendered = (() => {
    let off = 0;
    return slices.map((s) => {
      const len = (s.v / total) * c;
      const out = { ...s, len, off };
      off += len;
      return out;
    });
  })();
</script>

<div style="position: relative; width: {size}px; height: {size}px;">
  <svg width={size} height={size}>
    <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--bg-3)" stroke-width={thickness} fill="none"/>
    {#each rendered as s}
      <circle cx={size / 2} cy={size / 2} r={r} stroke={s.color}
        stroke-width={thickness} fill="none"
        stroke-dasharray="{s.len} {c - s.len}" stroke-dashoffset={-s.off}
        transform="rotate(-90 {size / 2} {size / 2})"/>
    {/each}
  </svg>
  <div class="center">
    <div>
      <div class="label" style="font-size: {size / 5}px;">{label}</div>
      {#if sub}<div class="sub mono">{sub}</div>{/if}
    </div>
  </div>
</div>

<style>
  .center { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; }
  .label { font-weight: 500; letter-spacing: -0.02em; }
  .sub { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; }
</style>
