<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  export let cell: number = 48;
  export let color: string = 'rgba(255,255,255,0.04)';

  let canvas: HTMLCanvasElement;
  let raf: number;
  let ro: ResizeObserver | null = null;

  onMount(() => {
    const ctx = canvas.getContext('2d')!;
    let w = 0, h = 0, off = 0;
    const fit = () => {
      const r = canvas.getBoundingClientRect();
      w = canvas.width = Math.max(1, Math.floor(r.width * devicePixelRatio));
      h = canvas.height = Math.max(1, Math.floor(r.height * devicePixelRatio));
    };
    fit();
    ro = new ResizeObserver(fit);
    ro.observe(canvas);

    const tick = () => {
      ctx.clearRect(0, 0, w, h);
      const step = cell * devicePixelRatio;
      off = (off + 0.2) % step;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = -step + off; x < w + step; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
      for (let y = -step + off; y < h + step; y += step) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();
      const sweepY = (Math.sin(performance.now() * 0.0004) * 0.5 + 0.5) * h;
      const grd = ctx.createLinearGradient(0, sweepY - 90 * devicePixelRatio, 0, sweepY + 90 * devicePixelRatio);
      grd.addColorStop(0, 'rgba(184,216,255,0)');
      grd.addColorStop(0.5, 'rgba(184,216,255,0.05)');
      grd.addColorStop(1, 'rgba(184,216,255,0)');
      ctx.fillStyle = grd;
      ctx.fillRect(0, sweepY - 90 * devicePixelRatio, w, 180 * devicePixelRatio);
      raf = requestAnimationFrame(tick);
    };
    tick();
  });

  onDestroy(() => {
    cancelAnimationFrame(raf);
    ro?.disconnect();
  });
</script>

<canvas bind:this={canvas} style="position: absolute; inset: 0; width: 100%; height: 100%;"></canvas>
