<script lang="ts">
  import '$lib/designkit/tokens.css';
  import { onMount } from 'svelte';
  import {
    VectorMark, ParticleField, LiveGrid,
    Widget, Button, Badge,
    Video, News, Market, Tickers, Weather, Clock, Calendar,
    Tasks, AgentLog, Vitals, Threat, Heat, Voice, Map,
    Waveform
  } from '$lib/designkit';
  import {
    fetchMarket, fetchNews, fetchTickers, fetchWeather, fetchThreat,
    fetchMap, fetchHeat, fetchVideo, fetchVitals, fetchCalendar,
    fetchTasks, fetchAgentLog, fetchVoice, fetchClock,
    defaultMarket, defaultNews, defaultTickers, defaultWeather, defaultThreat,
    defaultMap, defaultHeat, defaultVideo, defaultVitals, defaultCalendar,
    defaultTasks, defaultAgentLog, defaultVoice, defaultClock,
    type MarketData, type NewsData, type TickersData, type WeatherData,
    type ThreatData, type MapData, type HeatData, type VideoData,
    type VitalsData, type CalendarData, type TasksData, type AgentLogData,
    type VoiceData, type ClockData
  } from '$lib/designkit/api';

  // Each widget gets its own state cell. Defaults render immediately
  // (zero-state look while fetches resolve), real data swaps in on mount.
  let market: MarketData = defaultMarket;
  let news: NewsData = defaultNews;
  let tickers: TickersData = defaultTickers;
  let weather: WeatherData = defaultWeather;
  let threat: ThreatData = defaultThreat;
  let mapData: MapData = defaultMap;
  let heat: HeatData = defaultHeat;
  let video: VideoData = defaultVideo;
  let vitals: VitalsData = defaultVitals;
  let calendar: CalendarData = defaultCalendar;
  let tasks: TasksData = defaultTasks;
  let agentlog: AgentLogData = defaultAgentLog;
  let voice: VoiceData = defaultVoice;
  let clock: ClockData = defaultClock;

  let errors: Record<string, string> = {};
  let loading = true;

  async function safe<T>(key: string, fn: () => Promise<T>, fallback: T): Promise<T> {
    try {
      return await fn();
    } catch (e) {
      errors = { ...errors, [key]: (e as Error).message };
      return fallback;
    }
  }

  onMount(async () => {
    [market, news, tickers, weather, threat, mapData, heat, video,
     vitals, calendar, tasks, agentlog, voice, clock] = await Promise.all([
      safe('market',   fetchMarket,   defaultMarket),
      safe('news',     fetchNews,     defaultNews),
      safe('tickers',  fetchTickers,  defaultTickers),
      safe('weather',  fetchWeather,  defaultWeather),
      safe('threat',   fetchThreat,   defaultThreat),
      safe('map',      fetchMap,      defaultMap),
      safe('heat',     fetchHeat,     defaultHeat),
      safe('video',    fetchVideo,    defaultVideo),
      safe('vitals',   fetchVitals,   defaultVitals),
      safe('calendar', fetchCalendar, defaultCalendar),
      safe('tasks',    fetchTasks,    defaultTasks),
      safe('agentlog', fetchAgentLog, defaultAgentLog),
      safe('voice',    fetchVoice,    defaultVoice),
      safe('clock',    fetchClock,    defaultClock),
    ]);
    loading = false;
  });

  const initial = [
    { id: 'video',   x: 568, y: 16,  w: 360, h: 220 },
    { id: 'market',  x: 16,  y: 248, w: 360, h: 230 },
    { id: 'news',    x: 388, y: 248, w: 360, h: 230 },
    { id: 'tickers', x: 760, y: 248, w: 320, h: 230 },
    { id: 'weather', x: 1092,y: 16,  w: 280, h: 220 },
    { id: 'clock',   x: 1092,y: 248, w: 280, h: 230 },
    { id: 'calendar',x: 16,  y: 490, w: 360, h: 240 },
    { id: 'tasks',   x: 388, y: 490, w: 360, h: 240 },
    { id: 'agentlog',x: 760, y: 490, w: 612, h: 240 },
    { id: 'vitals',  x: 16,  y: 742, w: 360, h: 200 },
    { id: 'threat',  x: 388, y: 742, w: 360, h: 200 },
    { id: 'heat',    x: 760, y: 742, w: 360, h: 200 },
    { id: 'voice',   x: 1132,y: 742, w: 240, h: 200 }
  ];

  const TITLE: Record<string, string> = {
    video: 'video · live', news: 'intel feed', market: 'market',
    tickers: 'watchlist', weather: 'weather', clock: 'world clock',
    calendar: 'today', tasks: 'tasks', agentlog: 'agent log',
    vitals: 'vitals', threat: 'signal monitor', heat: 'activity heatmap',
    voice: 'voice'
  };

  let time = '';
  if (typeof window !== 'undefined') {
    setInterval(() => {
      time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    }, 1000);
  }
</script>

<div class="stage" data-testid="designkit-live">
  <div class="bg-grid"></div>
  <ParticleField density={0.000018} lineDist={140}/>

  <div class="osbar">
    <div class="left">
      <VectorMark size={16}/>
      <span class="title">Vector</span>
      <span class="mono build">v2.0 · LIVE</span>
    </div>
    <div class="right mono">
      <span><span class="ok" data-testid="status-uplink">●</span> UPLINK</span>
      <span data-testid="status-loading">{loading ? 'LOADING' : 'READY'}</span>
      <span>{time} PT</span>
    </div>
  </div>

  <Widget x={16} y={48} w={540} h={188} title="vector · live" noPad>
    <span slot="badge">
      {#if Object.keys(errors).length > 0}
        <Badge color="var(--warn)">{Object.keys(errors).length} offline</Badge>
      {:else}
        <Badge color="var(--ok)">nominal</Badge>
      {/if}
    </span>
    <div class="hero">
      <LiveGrid cell={32}/>
      <div class="hero-pad">
        <div class="hero-top">
          <VectorMark size={20}/>
          <span class="mono hero-eyebrow">LIVE DASHBOARD · WIRED TO /mock/*</span>
        </div>
        <div class="hero-body">
          <div class="hero-title"><span class="acc">Live.</span> {loading ? 'Loading…' : 'Wired.'}</div>
          <div class="hero-meta">
            All widgets pull from the backend's /mock/* endpoints.
            Replace the JSON files in /tmp-vector/mocks/ to customize fixtures.
          </div>
        </div>
        <div class="hero-foot">
          <span class="mono hero-time">{time}</span>
          <span class="hero-actions">
            <Button small mono>REFRESH</Button>
            <Button small mono kind="ghost">DESIGN</Button>
          </span>
        </div>
      </div>
    </div>
  </Widget>

  {#each initial as w (w.id)}
    <Widget x={w.x} y={w.y + 32} w={w.w} h={w.h} title={TITLE[w.id]}>
      {#if w.id === 'video'}    <Video data={video}/>
      {:else if w.id === 'market'}   <Market data={market}/>
      {:else if w.id === 'news'}     <News data={news}/>
      {:else if w.id === 'tickers'}  <Tickers data={tickers}/>
      {:else if w.id === 'weather'}  <Weather data={weather}/>
      {:else if w.id === 'clock'}    <Clock data={clock}/>
      {:else if w.id === 'calendar'} <Calendar data={calendar}/>
      {:else if w.id === 'tasks'}    <Tasks data={tasks}/>
      {:else if w.id === 'agentlog'} <AgentLog data={agentlog}/>
      {:else if w.id === 'vitals'}   <Vitals data={vitals}/>
      {:else if w.id === 'threat'}   <Threat data={threat}/>
      {:else if w.id === 'heat'}     <Heat data={heat}/>
      {:else if w.id === 'voice'}    <Voice data={voice}/>
      {/if}
    </Widget>
  {/each}

  <Widget x={1132} y={774} w={240} h={200} title="map">
    <Map data={mapData}/>
  </Widget>

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
