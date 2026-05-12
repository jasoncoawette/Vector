<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { fetchAudit, type AuditEntry } from '$lib/api';

  let entries: AuditEntry[] = [];
  let error = '';
  let loading = true;
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refresh() {
    try {
      entries = await fetchAudit(200);
      error = '';
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  function fmtTime(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString();
  }

  onMount(() => {
    refresh();
    timer = setInterval(refresh, 3000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<main>
  <h1>Audit log</h1>
  {#if loading}
    <p>Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if entries.length === 0}
    <p class="empty">no entries yet</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>time</th>
          <th>tool</th>
          <th>caller</th>
          <th>ok</th>
          <th>args</th>
          <th>result</th>
          <th>reason</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as e}
          <tr class:fail={!e.ok}>
            <td>{fmtTime(e.ts)}</td>
            <td class="tool">{e.tool}</td>
            <td>{e.caller}</td>
            <td>{e.ok ? '✓' : '✗'}</td>
            <td class="hash">{e.args_hash}</td>
            <td class="hash">{e.result_hash}</td>
            <td>{e.reason ?? ''}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</main>

<style>
  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem;
    font-family: system-ui, sans-serif;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  th,
  td {
    border-bottom: 1px solid #eee;
    padding: 0.4rem 0.5rem;
    text-align: left;
  }
  th {
    color: #6b7280;
    font-weight: 500;
  }
  .tool {
    font-weight: 600;
  }
  .hash {
    font-family: ui-monospace, monospace;
    color: #6b7280;
  }
  tr.fail {
    background: #fef2f2;
  }
  .error {
    color: #ef4444;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
</style>
