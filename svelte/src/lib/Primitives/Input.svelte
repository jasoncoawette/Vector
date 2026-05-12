<script lang="ts">
  export let placeholder: string = '';
  export let value: string = '';
  export let mono: boolean = false;
  export let icon: string = '›';
</script>

<div class="wrap">
  <span class="prefix">{icon}</span>
  <input class:mono bind:value {placeholder}/>
</div>

<style>
  .wrap {
    height: 36px; padding: 0 12px; border-radius: 10px;
    background: var(--bg-2); border: 1px solid var(--line);
    display: flex; align-items: center; gap: 8px;
  }
  .prefix { color: var(--vec); font-family: var(--font-mono); font-size: 11px; }
  input {
    background: transparent; border: 0; outline: none;
    color: var(--ink-0); font-size: 13px; width: 100%;
  }
  input.mono { font-family: var(--font-mono); }
</style>
