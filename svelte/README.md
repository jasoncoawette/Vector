# Vector — Design System

> The quiet operator. An AI personal assistant designed like Apple built it for a three-letter agency.

This package contains the Vector design system as **SvelteKit components**, design tokens, and brand guidelines.

```
svelte/
├─ src/
│  ├─ lib/
│  │  ├─ tokens.css              ← CSS variables (colors, type, radii)
│  │  ├─ index.ts                ← re-exports every component
│  │  ├─ Brand/
│  │  │  ├─ VectorMark.svelte
│  │  │  └─ Wordmark.svelte
│  │  ├─ Backgrounds/
│  │  │  ├─ ParticleField.svelte
│  │  │  ├─ LiveGrid.svelte
│  │  │  └─ RadarSweep.svelte
│  │  ├─ Primitives/
│  │  │  ├─ Button.svelte
│  │  │  ├─ Badge.svelte
│  │  │  ├─ Toggle.svelte
│  │  │  ├─ Input.svelte
│  │  │  └─ Tile.svelte
│  │  ├─ Charts/
│  │  │  ├─ Sparkline.svelte
│  │  │  ├─ AreaChart.svelte
│  │  │  ├─ Candles.svelte
│  │  │  ├─ StepLine.svelte
│  │  │  ├─ Heatmap.svelte
│  │  │  ├─ RadialBars.svelte
│  │  │  ├─ Donut.svelte
│  │  │  ├─ Ring.svelte
│  │  │  ├─ Bars.svelte
│  │  │  ├─ Waveform.svelte
│  │  │  └─ SegmentBar.svelte
│  │  ├─ Widget/
│  │  │  └─ Widget.svelte        ← resizable, draggable shell
│  │  └─ Widgets/
│  │     ├─ Video.svelte
│  │     ├─ News.svelte
│  │     ├─ Market.svelte
│  │     ├─ Tickers.svelte
│  │     ├─ Weather.svelte
│  │     ├─ Clock.svelte
│  │     ├─ Calendar.svelte
│  │     ├─ Tasks.svelte
│  │     ├─ AgentLog.svelte
│  │     ├─ Vitals.svelte
│  │     ├─ Threat.svelte
│  │     ├─ Heat.svelte
│  │     ├─ Voice.svelte
│  │     └─ Map.svelte
│  ├─ routes/
│  │  └─ +page.svelte            ← demo dashboard
│  └─ app.html
├─ BRAND.md                      ← brand guidelines, voice, do/don't
└─ package.json
```

## Install

```bash
cd svelte
pnpm install
pnpm dev
```

## Use a component

```svelte
<script>
  import { Widget, Market, VectorMark } from '$lib';
</script>

<Widget title="market · NVDA" x={16} y={16} w={360} h={240}>
  <Market/>
</Widget>
```

## Read the brand

See **[BRAND.md](./BRAND.md)** for principles, voice, mark usage, and clear-space rules.

The HTML design canvas at `Vector Design System.html` is the canonical reference for tokens, charts, and widget composition. Use it for visual audits and asset extraction.
