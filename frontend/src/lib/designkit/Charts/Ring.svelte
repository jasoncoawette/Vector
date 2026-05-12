<script lang="ts">
  export let pct: number = 72;
  export let color: string = 'var(--vec)';
  export let size: number = 84;
  export let label: string | null = null;
  export let sub: string = '';

  $: r = (size - 8) / 2;
  $: c = 2 * Math.PI * r;
</script>

<div style="position: relative; width: {size}px; height: {size}px;">
  <svg width={size} height={size}>
    <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.06)" stroke-width="4" fill="none"/>
    <circle cx={size / 2} cy={size / 2} r={r} stroke={color} stroke-width="4" fill="none"
      stroke-dasharray="{(c * pct) / 100} {c}" stroke-linecap="round"
      transform="rotate(-90 {size / 2} {size / 2})"/>
  </svg>
  <div class="center">
    <div class="num" style="font-size: {size / 4.2}px;">{label ?? pct + '%'}</div>
    {#if sub}<div class="sub mono">{sub}</div>{/if}
  </div>
</div>

<style>
  .center {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
  }
  .num { font-weight: 500; }
  .sub { font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em; }
</style>
