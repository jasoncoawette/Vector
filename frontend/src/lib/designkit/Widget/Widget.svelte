<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let x: number = 16;
  export let y: number = 16;
  export let w: number = 320;
  export let h: number = 200;
  export let title: string = '';
  export let minW: number = 200;
  export let minH: number = 140;
  export let footer: string | null = null;
  export let noPad: boolean = false;

  const GRID = 12;
  const snap = (v: number) => Math.round(v / GRID) * GRID;
  const dispatch = createEventDispatcher<{ change: { x: number; y: number; w: number; h: number } }>();

  function startDrag(e: MouseEvent, mode: 'drag' | 'resize') {
    e.preventDefault();
    const sx = e.clientX, sy = e.clientY;
    const start = { x, y, w, h };
    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      if (mode === 'drag') {
        x = Math.max(0, snap(start.x + dx));
        y = Math.max(0, snap(start.y + dy));
      } else {
        w = Math.max(minW, snap(start.w + dx));
        h = Math.max(minH, snap(start.h + dy));
      }
      dispatch('change', { x, y, w, h });
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }
</script>

<div class="widget" style="left: {x}px; top: {y}px; width: {w}px; height: {h}px;">
  <div class="head" on:mousedown={(e) => startDrag(e, 'drag')} role="toolbar">
    <div class="head-left">
      <span class="dots">
        <i></i><i></i><i></i>
      </span>
      <span class="title">{title}</span>
    </div>
    <slot name="badge"/>
  </div>

  <div class="body" class:noPad>
    <slot/>
  </div>

  {#if footer}<div class="foot mono">{footer}</div>{/if}

  <div class="handle" on:mousedown={(e) => startDrag(e, 'resize')}>
    <svg width="16" height="16" viewBox="0 0 16 16">
      <path d="M 12 4 L 4 12 M 12 8 L 8 12 M 12 12 L 11 13"
        stroke="var(--ink-3)" stroke-width="1" stroke-linecap="round"/>
    </svg>
  </div>
</div>

<style>
  .widget {
    position: absolute;
    background: var(--bg-1);
    border: 1px solid var(--line);
    border-radius: 12px; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px rgba(0,0,0,0.4);
  }
  .head {
    height: 30px; padding: 0 10px;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid var(--hair);
    cursor: grab; user-select: none; flex-shrink: 0;
  }
  .head:active { cursor: grabbing; }
  .head-left { display: flex; align-items: center; gap: 8px; }
  .dots { display: flex; gap: 3px; }
  .dots i {
    width: 5px; height: 5px; border-radius: 99px;
    background: var(--ink-4); display: inline-block;
  }
  .title {
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.22em;
    color: var(--ink-2); text-transform: uppercase;
  }
  .body {
    flex: 1; min-height: 0; padding: 12px; overflow: hidden; position: relative;
  }
  .body.noPad { padding: 0; }
  .foot {
    padding: 6px 10px; border-top: 1px solid var(--hair);
    font-size: 9.5px; color: var(--ink-3); letter-spacing: 0.18em;
    text-transform: uppercase; flex-shrink: 0;
  }
  .handle {
    position: absolute; right: 0; bottom: 0;
    width: 16px; height: 16px; cursor: nwse-resize;
  }
</style>
