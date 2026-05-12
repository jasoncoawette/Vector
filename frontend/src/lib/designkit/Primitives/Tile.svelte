<script lang="ts">
  export let title: string | null = null;
  export let right: string | null = null;
  export let footer: string | null = null;
  export let dense: boolean = false;
</script>

<div class="tile" class:dense>
  {#if title || right}
    <div class="head">
      {#if title}<span class="label">{title}</span>{/if}
      {#if right}<span class="right mono">{right}</span>{/if}
    </div>
  {/if}
  <div class="body"><slot/></div>
  {#if footer}<div class="foot mono">{footer}</div>{/if}
</div>

<style>
  .tile {
    padding: 14px; border-radius: 12px;
    background: var(--bg-1); border: 1px solid var(--line);
    display: flex; flex-direction: column; gap: 10px; min-width: 0;
  }
  .tile.dense { padding: 12px; gap: 8px; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  .body { min-width: 0; }
  .label {
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.22em;
    text-transform: uppercase; color: var(--ink-2);
  }
  .right, .foot { font-size: 10px; color: var(--ink-3); }
</style>
