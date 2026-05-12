<script lang="ts">
  export let on: boolean = false;
</script>

<button class="toggle" class:on on:click={() => (on = !on)} aria-pressed={on}>
  <span class="dot" style="left: {on ? 15 : 1}px;"></span>
</button>

<style>
  .toggle {
    width: 32px; height: 18px; border-radius: 999px; position: relative;
    background: var(--bg-3); border: 1px solid var(--line);
    cursor: pointer; padding: 0; transition: background 0.15s, border-color 0.15s;
  }
  .toggle.on { background: var(--vec); border-color: var(--vec); }
  .dot {
    position: absolute; top: 1px; width: 14px; height: 14px; border-radius: 99px;
    background: var(--ink-2); transition: left 0.15s;
  }
  .toggle.on .dot { background: #0a0b0d; }
</style>
