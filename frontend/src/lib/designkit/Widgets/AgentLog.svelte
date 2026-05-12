<script lang="ts">
  import type { AgentLogData } from '../api';

  export let data: AgentLogData | null = null;

  const fallback = [
    { t: '21:14:08', color: 'var(--ink-3)', text: 'Indexed 3 PDFs from inbox' },
    { t: '21:14:32', color: 'var(--ink-3)', text: 'Cross-referenced with Vault.notes/Q3' },
    { t: '21:14:41', color: 'var(--vec)',   text: 'Drafted reply to Mira (487 tokens)' },
    { t: '21:15:02', color: 'var(--ok)',    text: 'Confirmed table at Saburo · 7pm' },
    { t: '21:15:18', color: 'var(--ink-3)', text: 'Watching: GitHub auth-service, AWS billing' },
    { t: '21:15:44', color: 'var(--warn)',  text: 'Anomaly: us-west-2 cost +14% vs 7d avg' },
    { t: '21:16:02', color: 'var(--ink-3)', text: 'Context window: 412K / 1M' },
    { t: '21:16:19', color: 'var(--mag)',   text: 'Vault sync · 24 items · 1.4s' }
  ];

  $: lines = data?.lines?.length ? data.lines : fallback;
</script>

<div class="log mono">
  {#each lines as l}
    <div class="row">
      <span class="t">{l.t}</span>
      <span style="color: {l.color};">{l.text}</span>
    </div>
  {/each}
</div>

<style>
  .log { font-size: 11px; line-height: 1.7; height: 100%; overflow: auto; }
  .row { display: grid; grid-template-columns: 72px 1fr; gap: 10px; }
  .t { color: var(--ink-4); }
</style>
