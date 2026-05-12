<script lang="ts">
  const lines = [
    { t: '21:14:08', c: 'var(--ink-3)', l: 'Indexed 3 PDFs from inbox' },
    { t: '21:14:32', c: 'var(--ink-3)', l: 'Cross-referenced with Vault.notes/Q3' },
    { t: '21:14:41', c: 'var(--vec)',   l: 'Drafted reply to Mira (487 tokens)' },
    { t: '21:15:02', c: 'var(--ok)',    l: 'Confirmed table at Saburo · 7pm' },
    { t: '21:15:18', c: 'var(--ink-3)', l: 'Watching: GitHub auth-service, AWS billing' },
    { t: '21:15:44', c: 'var(--warn)',  l: 'Anomaly: us-west-2 cost +14% vs 7d avg' },
    { t: '21:16:02', c: 'var(--ink-3)', l: 'Context window: 412K / 1M' },
    { t: '21:16:19', c: 'var(--mag)',   l: 'Vault sync · 24 items · 1.4s' }
  ];
</script>

<div class="log mono">
  {#each lines as l}
    <div class="row">
      <span class="t">{l.t}</span>
      <span style="color: {l.c};">{l.l}</span>
    </div>
  {/each}
</div>

<style>
  .log { font-size: 11px; line-height: 1.7; height: 100%; overflow: auto; }
  .row { display: grid; grid-template-columns: 72px 1fr; gap: 10px; }
  .t { color: var(--ink-4); }
</style>
