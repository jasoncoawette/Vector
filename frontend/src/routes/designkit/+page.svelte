<script lang="ts">
  import '$lib/designkit/tokens.css';
  import {
    VectorMark, ParticleField, LiveGrid,
    Widget, Button, Badge,
    Video, News, Market, Tickers, Weather, Clock, Calendar,
    Tasks, AgentLog, Vitals, Threat, Heat, Voice, Map,
    Waveform
  } from '$lib/designkit';

  const initial = [
    { id: 'video',   x: 568, y: 16,  w: 360, h: 220, kind: 'video' },
    { id: 'market',  x: 16,  y: 248, w: 360, h: 230, kind: 'market' },
    { id: 'news',    x: 388, y: 248, w: 360, h: 230, kind: 'news' },
    { id: 'tickers', x: 760, y: 248, w: 320, h: 230, kind: 'tickers' },
    { id: 'weather', x: 1092,y: 16,  w: 280, h: 220, kind: 'weather' },
    { id: 'clock',   x: 1092,y: 248, w: 280, h: 230, kind: 'clock' },
    { id: 'calendar',x: 16,  y: 490, w: 360, h: 240, kind: 'calendar' },
    { id: 'tasks',   x: 388, y: 490, w: 360, h: 240, kind: 'tasks' },
    { id: 'agentlog',x: 760, y: 490, w: 612, h: 240, kind: 'agent' },
    { id: 'vitals',  x: 16,  y: 742, w: 360, h: 200, kind: 'vitals' },
    { id: 'threat',  x: 388, y: 742, w: 360, h: 200, kind: 'threat' },
    { id: 'heat',    x: 760, y: 742, w: 360, h: 200, kind: 'heat' },
    { id: 'voice',   x: 1132,y: 742, w: 240, h: 200, kind: 'voice' }
  ];

  let layout = initial;
  let time = '22:14';

  if (typeof window !== 'undefined') {
    setInterval(() => {
      time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    }, 1000);
  }

  const KIND_TITLE: Record<string, string> = {
    video: 'video · cam-04', news: 'intel feed', market: 'market · NVDA',
    tickers: 'watchlist', weather: 'weather', clock: 'world clock',
    calendar: 'today', tasks: 'tasks', agent: 'agent log',
    vitals: 'vitals', threat: 'signal monitor', heat: 'activity heatmap',
    voice: 'voice', map: 'location'
  };

  const KIND_COMP: Record<string, any> = {
    video: Video, news: News, market: Market, tickers: Tickers,
    weather: Weather, clock: Clock, calendar: Calendar, tasks: Tasks,
    agent: AgentLog, vitals: Vitals, threat: Threat, heat: Heat,
    voice: Voice, map: Map
  };

  function onChange(id: string, e: CustomEvent) {
    layout = layout.map((w) => (w.id === id ? { ...w, ...e.detail } : w));
  }
</script>

<div class="stage">
  <div class="bg-grid"></div>
  <ParticleField density={0.000018} lineDist={140}/>

  <!-- OS bar -->
  <div class="osbar">
    <div class="left">
      <VectorMark size={16}/>
      <span class="title">Vector</span>
      <span class="mono build">v2.0 · CLASSIFIED</span>
    </div>
    <div class="right mono">
      <span><span class="ok">●</span> UPLINK 14ms</span>
      <span>CTX 0.42M</span>
      <span>{time} PT</span>
      <span class="avatar">N</span>
    </div>
  </div>

  <!-- Hero widget -->
  <Widget x={16} y={48} w={540} h={188} title="vector · home" noPad
    on:change={(e) => { /* hero is not in layout list */ }}>
    <span slot="badge"><Badge color="var(--ok)">nominal</Badge></span>
    <div class="hero">
      <LiveGrid cell={32}/>
      <div class="hero-pad">
        <div class="hero-top">
          <VectorMark size={20}/>
          <span class="mono hero-eyebrow">GOOD EVENING, NIA · TUE 12 MAY</span>
        </div>
        <div class="hero-body">
          <div class="hero-title"><span class="acc">Quiet.</span> Three items need you.</div>
          <div class="hero-meta">Pricing v4 is with legal. Series B demo moved to 13:00. Mira asked for the onboarding numbers.</div>
        </div>
        <div class="hero-foot">
          <span class="mono hero-time">{time}</span>
          <span class="hero-actions">
            <Button small mono>ASK</Button>
            <Button small mono kind="ghost">BRIEF</Button>
          </span>
        </div>
      </div>
    </div>
  </Widget>

  <!-- All widgets -->
  {#each layout as w (w.id)}
    <Widget x={w.x} y={w.y + 32} w={w.w} h={w.h} title={KIND_TITLE[w.kind]}
      on:change={(e) => onChange(w.id, e)}>
      <svelte:component this={KIND_COMP[w.kind]}/>
    </Widget>
  {/each}

  <!-- Ask bar -->
  <div class="ask">
    <span class="orb"></span>
    <input placeholder="Ask Vector — try “show me my standup script”"/>
    <Waveform w={120} h={20}/>
    <span class="mono kbd">⌘K</span>
  </div>
</div>

<style>
  .stage {
    position: relative; width: 100vw; min-width: 1440px; height: 100vh; min-height: 980px;
    background: var(--bg-0); overflow: hidden;
  }
  .bg-grid {
    position: absolute; inset: 0;
    background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.05) 1px, transparent 1px);
    background-size: 24px 24px;
  }
  .osbar {
    position: absolute; top: 0; left: 0; right: 0; height: 32px;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 14px; background: rgba(10,11,13,0.6);
    backdrop-filter: blur(20px) saturate(140%);
    border-bottom: 1px solid var(--line); z-index: 10;
  }
  .left { display: flex; align-items: center; gap: 12px; }
  .title { font-size: 12px; font-weight: 500; }
  .build { font-size: 10px; color: var(--ink-3); letter-spacing: 0.18em; }
  .right { display: flex; align-items: center; gap: 14px; font-size: 10px; color: var(--ink-2); }
  .ok { color: var(--ok); }
  .avatar {
    width: 22px; height: 22px; border-radius: 99px; display: grid; place-items: center;
    background: linear-gradient(135deg, #3b3f49, #1f242d);
    border: 1px solid var(--line); font-size: 9px; color: var(--ink-1);
  }

  .hero { position: relative; width: 100%; height: 100%; overflow: hidden; }
  .hero-pad {
    position: absolute; inset: 0; padding: 18px;
    display: flex; flex-direction: column; justify-content: space-between;
  }
  .hero-top { display: flex; align-items: center; gap: 10px; }
  .hero-eyebrow { font-size: 10px; color: var(--ink-3); letter-spacing: 0.24em; }
  .hero-title { font-size: 32px; font-weight: 300; letter-spacing: -0.025em; line-height: 1.05; }
  .hero-title .acc { color: var(--vec); }
  .hero-meta { color: var(--ink-2); font-size: 13px; margin-top: 8px; max-width: 460px; }
  .hero-foot { display: flex; justify-content: space-between; align-items: center; }
  .hero-time { font-size: 24px; color: var(--ink-0); letter-spacing: 0.04em; }
  .hero-actions { display: flex; gap: 6px; }

  .ask {
    position: absolute; left: 16px; right: 16px; bottom: 16px;
    height: 46px; padding: 0 14px; border-radius: 12px;
    background: rgba(10,11,13,0.7); border: 1px solid var(--line-strong);
    backdrop-filter: blur(20px) saturate(160%);
    display: flex; align-items: center; gap: 12px; z-index: 11;
  }
  .orb { width: 8px; height: 8px; border-radius: 99px; background: var(--vec); }
  .ask input {
    flex: 1; background: transparent; border: 0; outline: 0;
    color: var(--ink-0); font-size: 14px;
  }
  .kbd { font-size: 10px; color: var(--ink-3); letter-spacing: 0.16em; }
</style>
