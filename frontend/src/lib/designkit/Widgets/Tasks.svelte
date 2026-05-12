<script lang="ts">
  import Badge from '../Primitives/Badge.svelte';
  import type { TasksData } from '../api';

  export let data: TasksData | null = null;

  const fallback = [
    { done: true,  label: 'Send pricing v4 to legal',   meta: 'Drafted by Vector' },
    { done: false, label: "Review Anya's onboarding",   meta: 'Due 17:00', flag: 'warn' as const },
    { done: false, label: 'Approve Q2 spend',           meta: '3 line items' },
    { done: false, label: 'Reply to investor intro',    meta: '2 days idle', flag: 'crit' as const }
  ];

  $: list = data?.items?.length ? data.items : fallback;
</script>

<div class="wrap">
  {#each list as t, i}
    <div class="row" class:last={i === list.length - 1}>
      <div class="check" class:on={t.done}>{t.done ? '✓' : ''}</div>
      <div class="text">
        <div class="lbl" class:done={t.done}>{t.label}</div>
        <div class="meta mono">{t.meta}</div>
      </div>
      {#if t.flag}
        <Badge color={`var(--${t.flag})`}>{t.flag === 'crit' ? 'OVERDUE' : 'TODAY'}</Badge>
      {/if}
    </div>
  {/each}
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: 100%; }
  .row {
    display: flex; gap: 10px; align-items: center; padding: 8px 0;
    border-bottom: 1px solid var(--hair);
  }
  .row.last { border-bottom: none; }
  .check {
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid var(--line-strong); background: transparent;
    display: grid; place-items: center; font-size: 10px; color: #0a0b0d;
  }
  .check.on { background: var(--vec); }
  .text { flex: 1; }
  .lbl { font-size: 13px; color: var(--ink-0); }
  .lbl.done { color: var(--ink-3); text-decoration: line-through; }
  .meta { font-size: 10px; color: var(--ink-3); }
</style>
