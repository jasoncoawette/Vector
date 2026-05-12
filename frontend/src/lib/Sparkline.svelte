<script lang="ts">
  export let values: number[] = [];
  export let width = 160;
  export let height = 40;
  export let color = '#3b82f6';

  $: points = (() => {
    if (values.length === 0) return '';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = values.length === 1 ? 0 : width / (values.length - 1);
    return values
      .map((v, i) => {
        const x = i * step;
        const y = height - ((v - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  })();
</script>

<svg viewBox="0 0 {width} {height}" {width} {height} aria-hidden="true">
  {#if values.length > 1}
    <polyline fill="none" stroke={color} stroke-width="1.5" points={points} />
  {:else if values.length === 1}
    <circle cx={width / 2} cy={height / 2} r="2.5" fill={color} />
  {/if}
</svg>

<style>
  svg {
    display: block;
  }
</style>
