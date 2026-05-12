import { describe, it, expect, vi } from 'vitest';
import {
  fetchMarket, fetchNews, fetchTickers, fetchWeather, fetchThreat,
  fetchMap, fetchHeat, fetchVideo, fetchVitals, fetchCalendar,
  fetchTasks, fetchAgentLog, fetchVoice, fetchClock,
  defaultMarket, defaultNews, defaultTickers, defaultWeather, defaultThreat,
  defaultMap, defaultHeat, defaultVideo, defaultVitals, defaultCalendar,
  defaultTasks, defaultAgentLog, defaultVoice, defaultClock,
} from './api';

function ok<T>(body: T) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  });
}

function fail(status: number) {
  return vi.fn().mockResolvedValue({ ok: false, status });
}

describe('designkit/api fetchers — happy path', () => {
  it('fetchMarket parses payload', async () => {
    const f = ok({
      symbol: 'NVDA', exchange: 'NASDAQ',
      price: 100, delta_abs: 1, delta_pct: 1,
      ranges: ['1D'], active_range: '1D',
      stats: { open: 1, high: 2, vol: '1M', pe: 10 },
      candles: [{ o: 1, h: 2, l: 0.5, c: 1.5 }]
    });
    const r = await fetchMarket(f as unknown as typeof fetch);
    expect(r.symbol).toBe('NVDA');
    expect(r.candles[0].c).toBe(1.5);
    expect(f).toHaveBeenCalledWith(expect.stringContaining('/mock/market'));
  });

  it('fetchNews parses items', async () => {
    const f = ok({ items: [{ src: 'X', headline: 'h', age: '1m', tag: 'A' }] });
    const r = await fetchNews(f as unknown as typeof fetch);
    expect(r.items[0].headline).toBe('h');
  });

  it('fetchTickers parses items', async () => {
    const f = ok({ items: [{ sym: 'BTC', px: '1', ch: -1.2, spark: [1, 2, 3] }] });
    const r = await fetchTickers(f as unknown as typeof fetch);
    expect(r.items[0].ch).toBe(-1.2);
  });

  it('fetchWeather parses hourly', async () => {
    const f = ok({
      location: 'SF', condition: 'CLEAR',
      temp_f: 60, high_f: 70, low_f: 50, feels_f: 60,
      hourly: [{ t: 'NOW', temp_f: 60 }]
    });
    const r = await fetchWeather(f as unknown as typeof fetch);
    expect(r.hourly).toHaveLength(1);
  });

  it('fetchThreat parses series', async () => {
    const f = ok({
      label: 'L', title: 'T', severity: 'ELEVATED',
      threshold: 0.5, series: [0.1, 0.6], anomalies_at: ['00:00']
    });
    const r = await fetchThreat(f as unknown as typeof fetch);
    expect(r.severity).toBe('ELEVATED');
    expect(r.series).toEqual([0.1, 0.6]);
  });

  it('fetchMap parses markers', async () => {
    const f = ok({
      center: { lat: 1, lon: 2 },
      markers: [{ x: 1, y: 2, color: 'red', label: 'A' }]
    });
    const r = await fetchMap(f as unknown as typeof fetch);
    expect(r.markers[0].label).toBe('A');
  });

  it('fetchHeat parses 7x24 grid', async () => {
    const f = ok({
      label: 'L', title: 'T', total_hours: 50,
      grid: [[0.1, 0.2], [0.3, 0.4]],
      scale_min: 0, scale_max: 8
    });
    const r = await fetchHeat(f as unknown as typeof fetch);
    expect(r.grid).toHaveLength(2);
  });

  it('fetchVideo parses metadata', async () => {
    const f = ok({
      camera: 'A', status: 'LIVE', elapsed: '00:00:00',
      resolution: '1080p', fps: 30, progress: 0.5,
      elapsed_short: '00:00', remaining: '00:00'
    });
    const r = await fetchVideo(f as unknown as typeof fetch);
    expect(r.progress).toBe(0.5);
  });

  it('fetchVitals parses metrics', async () => {
    const f = ok({
      metrics: [
        { key: 'hr', pct: 50, label: '60', sub: 'HR',
          heading: 'RESTING', meta: 'm', color: 'c' }
      ]
    });
    const r = await fetchVitals(f as unknown as typeof fetch);
    expect(r.metrics[0].key).toBe('hr');
  });

  it('fetchCalendar parses events', async () => {
    const f = ok({
      events: [{ t: '09:00', title: 'X', color: 'c', live: true, dur: '15m' }]
    });
    const r = await fetchCalendar(f as unknown as typeof fetch);
    expect(r.events[0].live).toBe(true);
  });

  it('fetchTasks parses items', async () => {
    const f = ok({
      items: [{ done: false, label: 'X', meta: 'm', flag: 'crit' }]
    });
    const r = await fetchTasks(f as unknown as typeof fetch);
    expect(r.items[0].flag).toBe('crit');
  });

  it('fetchAgentLog parses lines', async () => {
    const f = ok({ lines: [{ t: '00:00:01', color: 'c', text: 't' }] });
    const r = await fetchAgentLog(f as unknown as typeof fetch);
    expect(r.lines[0].text).toBe('t');
  });

  it('fetchVoice parses transcript', async () => {
    const f = ok({ status: 'LISTENING', transcript: 'hi' });
    const r = await fetchVoice(f as unknown as typeof fetch);
    expect(r.transcript).toBe('hi');
  });

  it('fetchClock parses zones', async () => {
    const f = ok({ zones: [{ name: 'NEW YORK', time: '12:00' }] });
    const r = await fetchClock(f as unknown as typeof fetch);
    expect(r.zones[0].name).toBe('NEW YORK');
  });
});

describe('designkit/api fetchers — failure', () => {
  it.each([
    ['market', fetchMarket],
    ['news', fetchNews],
    ['tickers', fetchTickers],
    ['weather', fetchWeather],
    ['threat', fetchThreat],
    ['map', fetchMap],
    ['heat', fetchHeat],
    ['video', fetchVideo],
    ['vitals', fetchVitals],
    ['calendar', fetchCalendar],
    ['tasks', fetchTasks],
    ['agentlog', fetchAgentLog],
    ['voice', fetchVoice],
    ['clock', fetchClock],
  ])('%s throws on non-200', async (_name, fn) => {
    await expect(fn(fail(500) as unknown as typeof fetch)).rejects.toThrow();
  });
});

describe('designkit/api defaults', () => {
  it('all defaults parse into their respective shapes', () => {
    expect(defaultMarket.symbol).toBe('NVDA');
    expect(defaultNews.items).toEqual([]);
    expect(defaultTickers.items).toEqual([]);
    expect(defaultWeather.location).toBe('SAN FRANCISCO');
    expect(defaultThreat.severity).toBe('NOMINAL');
    expect(defaultMap.center.lat).toBeCloseTo(37.7749);
    expect(defaultHeat.grid).toEqual([]);
    expect(defaultVideo.status).toBe('OFFLINE');
    expect(defaultVitals.metrics).toEqual([]);
    expect(defaultCalendar.events).toEqual([]);
    expect(defaultTasks.items).toEqual([]);
    expect(defaultAgentLog.lines).toEqual([]);
    expect(defaultVoice.status).toBe('IDLE');
    expect(defaultClock.zones).toEqual([]);
  });
});
