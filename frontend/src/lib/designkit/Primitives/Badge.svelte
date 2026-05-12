<script lang="ts">
  export let color: string = 'var(--vec)';
  export let solid: boolean = false;
  export let dim: boolean = false;
</script>

<span class="badge" class:solid class:dim
  style="--c: {color}; background: {solid ? color : 'transparent'};
         color: {solid ? '#0a0b0d' : (dim ? 'var(--ink-2)' : color)};
         border: {solid ? 'none' : `1px solid ${dim ? 'var(--line)' : color + '55'}`};">
  {#if !solid}<span class="dot" style="background: {color};"></span>{/if}
  <slot/>
</span>

<style>
  .badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 2px 7px; border-radius: 999px;
    font-family: var(--font-mono); font-size: 10px;
    letter-spacing: 0.16em; text-transform: uppercase;
  }
  .dot { width: 4px; height: 4px; border-radius: 99px; }
</style>
