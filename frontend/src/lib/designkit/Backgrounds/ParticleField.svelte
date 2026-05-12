<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  export let density: number = 0.00009;
  export let lineDist: number = 120;
  export let color: string = 'rgba(184,216,255,0.45)';

  let canvas: HTMLCanvasElement;
  let raf: number;
  let ro: ResizeObserver | null = null;

  onMount(() => {
    const ctx = canvas.getContext('2d')!;
    let w = 0, h = 0;
    let parts: { x: number; y: number; vx: number; vy: number; r: number }[] = [];

    const fit = () => {
      const r = canvas.getBoundingClientRect();
      w = canvas.width = Math.max(1, Math.floor(r.width * devicePixelRatio));
      h = canvas.height = Math.max(1, Math.floor(r.height * devicePixelRatio));
      const n = Math.max(20, Math.floor(w * h * density));
      parts = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18 * devicePixelRatio,
        vy: (Math.random() - 0.5) * 0.18 * devicePixelRatio,
        r: (0.6 + Math.random() * 1.4) * devicePixelRatio
      }));
    };
    fit();
    ro = new ResizeObserver(fit);
    ro.observe(canvas);

    const tick = () => {
      ctx.clearRect(0, 0, w, h);
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
      }
      for (let i = 0; i < parts.length; i++) {
        for (let j = i + 1; j < parts.length; j++) {
          const dx = parts[i].x - parts[j].x, dy = parts[i].y - parts[j].y;
          const d = Math.hypot(dx, dy);
          if (d < lineDist * devicePixelRatio) {
            const o = (1 - d / (lineDist * devicePixelRatio)) * 0.5;
            ctx.strokeStyle = `rgba(184,216,255,${o.toFixed(3)})`;
            ctx.beginPath();
            ctx.moveTo(parts[i].x, parts[i].y);
            ctx.lineTo(parts[j].x, parts[j].y);
            ctx.stroke();
          }
        }
      }
      ctx.fillStyle = color;
      for (const p of parts) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
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
