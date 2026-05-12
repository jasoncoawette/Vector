<script lang="ts">
  export let kind: 'primary' | 'accent' | 'ghost' | 'quiet' | 'danger' = 'primary';
  export let mono: boolean = false;
  export let small: boolean = false;
</script>

<button class="btn {kind}" class:mono class:small on:click>
  <slot/>
</button>

<style>
  .btn {
    display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
    height: 34px; padding: 0 14px; border-radius: 8px;
    font-size: 13px; font-weight: 500;
  }
  .btn.small { height: 28px; padding: 0 10px; font-size: 12px; }
  .btn.mono { font-family: var(--font-mono); letter-spacing: 0.1em; text-transform: uppercase; }
  .btn.primary { background: var(--ink-0); color: #0a0b0d; border: 1px solid var(--ink-0); }
  .btn.accent { background: transparent; color: var(--vec); border: 1px solid rgba(184,216,255,0.4); }
  .btn.ghost { background: transparent; color: var(--ink-0); border: 1px solid var(--line-strong); }
  .btn.quiet { background: var(--bg-3); color: var(--ink-0); border: 1px solid var(--line); }
  .btn.danger { background: transparent; color: var(--crit); border: 1px solid rgba(217,122,122,0.4); }
</style>
