<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    fetchPlan,
    listPlans,
    submitPlan,
    type PlanRunSnapshot,
    type PlanStepStatus,
    type StepRunSnapshot
  } from '$lib/api';

  // ---- live state ----
  let plans: PlanRunSnapshot[] = [];
  let selected: PlanRunSnapshot | null = null;
  let selectedId: string | null = null;
  let error = '';
  let listError = '';
  let timer: ReturnType<typeof setInterval> | null = null;

  // ---- submit form ----
  const PROMPT_PRESETS: { label: string; goal: string; steps: any[] }[] = [
    {
      label: 'Research → draft',
      goal: 'Research AFWERX SBIR phase II and draft an application outline',
      steps: [
        {
          id: 1,
          agent: 'research',
          prompt: 'Find current AFWERX SBIR phase II requirements and deadlines.'
        },
        {
          id: 2,
          agent: 'writer',
          prompt: 'Draft an outline for a Stratus application based on {{step_1.output}}.',
          depends_on: [1]
        }
      ]
    },
    {
      label: 'Code → test → security',
      goal: 'Ship a small change with tests and a security audit',
      steps: [
        {
          id: 1,
          agent: 'code',
          prompt: 'Implement the change.',
          success_criteria: 'tests pass, no new lints'
        },
        {
          id: 2,
          agent: 'tester',
          prompt: 'Cover the change in {{step_1.output}} with one happy-path test and one edge case.',
          depends_on: [1]
        },
        {
          id: 3,
          agent: 'security',
          prompt: 'Audit the diff for OWASP top-10 and ITAR violations: {{step_1.output}}',
          depends_on: [1]
        }
      ]
    }
  ];

  let showForm = false;
  let goal = PROMPT_PRESETS[0].goal;
  let stepsJson = JSON.stringify(PROMPT_PRESETS[0].steps, null, 2);
  let token = '';
  let submitting = false;

  function loadToken() {
    if (typeof localStorage !== 'undefined') {
      token = localStorage.getItem('vector.token') ?? '';
    }
  }
  function saveToken(t: string) {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('vector.token', t);
    }
  }

  // ---- color + format helpers ----
  const STATUS_COLOR: Record<PlanStepStatus, string> = {
    pending: '#9ca3af',
    ready: '#9ca3af',
    running: '#3b82f6',
    done: '#22c55e',
    failed: '#ef4444',
    skipped: '#f59e0b'
  };

  function fmtUsd(v: number): string {
    return `$${v.toFixed(3)}`;
  }
  function fmtTime(ts: number | null): string {
    if (ts === null) return '—';
    return new Date(ts * 1000).toLocaleTimeString();
  }
  function elapsed(s: StepRunSnapshot): string {
    if (s.started_at === null) return '—';
    const end = s.ended_at ?? Date.now() / 1000;
    const secs = end - s.started_at;
    return secs > 60 ? `${(secs / 60).toFixed(1)}m` : `${secs.toFixed(1)}s`;
  }

  // ---- polling ----
  async function refresh() {
    try {
      plans = (await listPlans()).sort((a, b) => b.plan.created_at - a.plan.created_at);
      listError = '';
      if (selectedId) {
        try {
          selected = await fetchPlan(selectedId);
        } catch (e) {
          // selected may have rotated out of an in-memory store
          error = (e as Error).message;
        }
      }
    } catch (e) {
      listError = (e as Error).message;
    }
  }

  function select(id: string) {
    selectedId = id;
    error = '';
    refresh();
  }

  function loadPreset(idx: number) {
    goal = PROMPT_PRESETS[idx].goal;
    stepsJson = JSON.stringify(PROMPT_PRESETS[idx].steps, null, 2);
  }

  async function submit() {
    if (submitting) return;
    submitting = true;
    error = '';
    try {
      const steps = JSON.parse(stepsJson);
      const result = await submitPlan({ goal, steps }, token || null);
      selectedId = result.plan.id;
      saveToken(token);
      showForm = false;
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      submitting = false;
    }
  }

  onMount(() => {
    loadToken();
    refresh();
    timer = setInterval(refresh, 2000);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
  });
</script>

<main>
  <header>
    <h1>Plans</h1>
    <button class="new" on:click={() => (showForm = !showForm)}>
      {showForm ? 'Cancel' : 'New plan'}
    </button>
  </header>

  {#if showForm}
    <section class="form">
      <div class="presets">
        {#each PROMPT_PRESETS as p, i}
          <button class="preset" type="button" on:click={() => loadPreset(i)}>
            {p.label}
          </button>
        {/each}
      </div>
      <label>
        Goal
        <input type="text" bind:value={goal} placeholder="Goal of this plan" />
      </label>
      <label>
        Steps (JSON)
        <textarea bind:value={stepsJson} rows="14" spellcheck="false"></textarea>
      </label>
      <label>
        Bearer token (only if backend requires it)
        <input type="password" bind:value={token} placeholder="optional" />
      </label>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="primary" on:click={submit} disabled={submitting}>
        {submitting ? 'Submitting…' : 'Submit plan'}
      </button>
    </section>
  {/if}

  <div class="layout">
    <aside class="list">
      <h2>Recent</h2>
      {#if listError}
        <p class="error">{listError}</p>
      {:else if plans.length === 0}
        <p class="empty">no plans yet</p>
      {:else}
        <ul>
          {#each plans as p (p.plan.id)}
            <li
              class:active={p.plan.id === selectedId}
              on:click={() => select(p.plan.id)}
              role="button"
              tabindex="0"
              on:keydown={(e) => e.key === 'Enter' && select(p.plan.id)}
            >
              <div class="title">{p.plan.goal}</div>
              <div class="meta">
                <span class={`pill pill-${p.status}`}>{p.status}</span>
                <span class="cost">{fmtUsd(p.total_cost_usd)}</span>
                <span class="steps-count">{p.steps.length} step{p.steps.length === 1 ? '' : 's'}</span>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </aside>

    <section class="detail">
      {#if !selected}
        <p class="empty">select a plan</p>
      {:else}
        <h2>{selected.plan.goal}</h2>
        <div class="meta-row">
          <span class={`pill pill-${selected.status}`}>{selected.status}</span>
          <span class="cost">{fmtUsd(selected.total_cost_usd)} total</span>
          <span class="when">started {fmtTime(selected.started_at)}</span>
          {#if selected.ended_at}
            <span class="when">ended {fmtTime(selected.ended_at)}</span>
          {/if}
        </div>
        {#if selected.error}
          <p class="error">{selected.error}</p>
        {/if}

        <ol class="dag">
          {#each selected.steps as step (step.step_id)}
            {@const def = selected.plan.steps.find((s) => s.id === step.step_id)}
            <li class={`step status-${step.status}`}>
              <div class="step-head">
                <span class="dot" style:background={STATUS_COLOR[step.status]}></span>
                <span class="id">#{step.step_id}</span>
                <span class="agent">{def?.agent}</span>
                <span class="step-status">{step.status}</span>
                {#if def?.depends_on && def.depends_on.length > 0}
                  <span class="deps">after {def.depends_on.map((d) => `#${d}`).join(', ')}</span>
                {/if}
                <span class="step-cost">{fmtUsd(step.cost_usd)} · {elapsed(step)}</span>
              </div>
              <div class="prompt">{def?.prompt}</div>
              {#if step.output}
                <pre class="output">{step.output}</pre>
              {/if}
              {#if step.error}
                <p class="step-error">{step.error}</p>
              {/if}
            </li>
          {/each}
        </ol>
      {/if}
    </section>
  </div>
</main>

<style>
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 1.5rem;
    font-family: system-ui, sans-serif;
  }
  header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  header h1 {
    margin: 0;
    flex: 1;
  }
  .new {
    height: 36px;
    padding: 0 0.9rem;
    border: 1px solid #d1d5db;
    background: white;
    border-radius: 8px;
    cursor: pointer;
  }
  .form {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .presets {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .preset {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
    cursor: pointer;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8rem;
    color: #6b7280;
  }
  input,
  textarea {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 0.5rem 0.6rem;
    font-size: 0.9rem;
    font-family: inherit;
  }
  textarea {
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .primary {
    align-self: flex-start;
    background: #111827;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1.2rem;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .primary:disabled {
    opacity: 0.5;
  }
  .layout {
    display: grid;
    grid-template-columns: minmax(220px, 280px) 1fr;
    gap: 1.5rem;
  }
  aside.list h2,
  section.detail h2 {
    margin: 0 0 0.5rem;
    font-size: 0.85rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  aside.list ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  aside.list li {
    padding: 0.5rem 0.7rem;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    background: white;
  }
  aside.list li.active {
    border-color: #111827;
  }
  aside.list li .title {
    font-size: 0.85rem;
    line-height: 1.3;
    margin-bottom: 0.3rem;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  aside.list li .meta {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    flex-wrap: wrap;
    font-size: 0.7rem;
    color: #6b7280;
  }
  .pill {
    padding: 0.05rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: white;
  }
  .pill-running {
    background: #3b82f6;
  }
  .pill-done {
    background: #22c55e;
  }
  .pill-failed {
    background: #ef4444;
  }
  .pill-pending,
  .pill-partial {
    background: #9ca3af;
  }
  .cost {
    font-family: ui-monospace, monospace;
  }
  section.detail .meta-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    color: #6b7280;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    flex-wrap: wrap;
  }
  .dag {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .step {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    background: white;
  }
  .step.status-running {
    border-color: #3b82f6;
    background: #eff6ff;
  }
  .step.status-failed,
  .step.status-skipped {
    background: #fef2f2;
  }
  .step.status-done {
    background: #f0fdf4;
  }
  .step-head {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    font-size: 0.8rem;
    color: #6b7280;
    flex-wrap: wrap;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .id {
    font-family: ui-monospace, monospace;
    color: #111827;
    font-weight: 600;
  }
  .agent {
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.7rem;
    color: #111827;
  }
  .deps {
    font-style: italic;
  }
  .step-cost {
    margin-left: auto;
    font-family: ui-monospace, monospace;
  }
  .prompt {
    margin-top: 0.4rem;
    font-size: 0.9rem;
    color: #111827;
    white-space: pre-wrap;
  }
  .output {
    margin: 0.5rem 0 0;
    padding: 0.6rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    font-size: 0.78rem;
    white-space: pre-wrap;
    max-height: 220px;
    overflow: auto;
  }
  .step-error {
    margin: 0.4rem 0 0;
    color: #b91c1c;
    font-size: 0.8rem;
  }
  .empty {
    color: #6b7280;
    font-style: italic;
  }
  .error {
    color: #b91c1c;
    margin: 0.4rem 0;
  }
  @media (max-width: 768px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
</style>
