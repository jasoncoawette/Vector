// Designkit data adapters — fetch from the Vector backend and return
// strongly-typed shapes consumed by widgets. The /mock/* endpoints serve
// deterministic stand-ins until real keys are wired in. Each adapter has
// a `default*` fallback so widgets keep rendering when the backend is
// offline (e.g. during SSR or in a frontend-only Storybook run).

const DEFAULT_BACKEND =
  typeof window !== 'undefined' && window.location.port === '5173'
    ? `http://${window.location.hostname}:7777`
    : '';

function baseUrl(): string {
  // Vite exposes import.meta.env.VITE_BACKEND at build time.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fromEnv = (import.meta as any)?.env?.VITE_BACKEND as string | undefined;
  return fromEnv ?? DEFAULT_BACKEND;
}

async function getJson<T>(path: string, f: typeof fetch = fetch): Promise<T> {
  const res = await f(`${baseUrl()}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

// ----- Shapes -----

export interface Candle { o: number; h: number; l: number; c: number; }
export interface MarketData {
  symbol: string; exchange: string;
  price: number; delta_abs: number; delta_pct: number;
  ranges: string[]; active_range: string;
  stats: { open: number; high: number; vol: string; pe: number; };
  candles: Candle[];
}

export interface NewsItem { src: string; headline: string; age: string; tag: string; }
export interface NewsData { items: NewsItem[]; }

export interface TickerItem { sym: string; px: string; ch: number; spark: number[]; }
export interface TickersData { items: TickerItem[]; }

export interface WeatherHour { t: string; temp_f: number; }
export interface WeatherData {
  location: string; condition: string;
  temp_f: number; high_f: number; low_f: number; feels_f: number;
  hourly: WeatherHour[];
}

export interface ThreatData {
  label: string; title: string; severity: string;
  threshold: number; series: number[]; anomalies_at: string[];
}

export interface MapMarker { x: number; y: number; color: string; label: string; }
export interface MapData {
  center: { lat: number; lon: number };
  markers: MapMarker[];
}

export interface HeatData {
  label: string; title: string; total_hours: number;
  grid: number[][]; scale_min: number; scale_max: number;
}

export interface VideoData {
  camera: string; status: string; elapsed: string;
  resolution: string; fps: number;
  progress: number; elapsed_short: string; remaining: string;
}

export interface VitalsMetric {
  key: string; pct: number; label: string; sub: string;
  heading: string; meta: string; color: string;
}
export interface VitalsData { metrics: VitalsMetric[]; }

export interface CalendarEvent {
  t: string; title: string; color: string; live: boolean; dur: string;
}
export interface CalendarData { events: CalendarEvent[]; }

export interface TaskItem {
  done: boolean; label: string; meta: string; flag?: 'warn' | 'crit';
}
export interface TasksData { items: TaskItem[]; }

export interface AgentLogLine { t: string; color: string; text: string; }
export interface AgentLogData { lines: AgentLogLine[]; }

export interface VoiceData { status: string; transcript: string; }

export interface ClockZone { name: string; time: string; }
export interface ClockData { zones: ClockZone[]; }

// ----- Fetchers -----

export const fetchMarket   = (f: typeof fetch = fetch) => getJson<MarketData>('/mock/market', f);
export const fetchNews     = (f: typeof fetch = fetch) => getJson<NewsData>('/mock/news', f);
export const fetchTickers  = (f: typeof fetch = fetch) => getJson<TickersData>('/mock/tickers', f);
export const fetchWeather  = (f: typeof fetch = fetch) => getJson<WeatherData>('/mock/weather', f);
export const fetchThreat   = (f: typeof fetch = fetch) => getJson<ThreatData>('/mock/threat', f);
export const fetchMap      = (f: typeof fetch = fetch) => getJson<MapData>('/mock/map', f);
export const fetchHeat     = (f: typeof fetch = fetch) => getJson<HeatData>('/mock/heat', f);
export const fetchVideo    = (f: typeof fetch = fetch) => getJson<VideoData>('/mock/video', f);
export const fetchVitals   = (f: typeof fetch = fetch) => getJson<VitalsData>('/mock/vitals', f);
export const fetchCalendar = (f: typeof fetch = fetch) => getJson<CalendarData>('/mock/calendar', f);
export const fetchTasks    = (f: typeof fetch = fetch) => getJson<TasksData>('/mock/tasks', f);
export const fetchAgentLog = (f: typeof fetch = fetch) => getJson<AgentLogData>('/mock/agentlog', f);
export const fetchVoice    = (f: typeof fetch = fetch) => getJson<VoiceData>('/mock/voice', f);
export const fetchClock    = (f: typeof fetch = fetch) => getJson<ClockData>('/mock/clock', f);

// ----- Defaults (offline / SSR fallback) -----

export const defaultMarket: MarketData = {
  symbol: 'NVDA', exchange: 'NASDAQ',
  price: 1142.08, delta_abs: 18.42, delta_pct: 1.64,
  ranges: ['1D', '1W', '1M', '1Y'], active_range: '1M',
  stats: { open: 1124.10, high: 1148.92, vol: '38.4M', pe: 62.1 },
  candles: [],
};
export const defaultNews: NewsData = { items: [] };
export const defaultTickers: TickersData = { items: [] };
export const defaultWeather: WeatherData = {
  location: 'SAN FRANCISCO', condition: 'CLEAR',
  temp_f: 62, high_f: 68, low_f: 54, feels_f: 60, hourly: [],
};
export const defaultThreat: ThreatData = {
  label: 'SIGNAL · OFFLINE', title: 'no data', severity: 'NOMINAL',
  threshold: 0.65, series: [], anomalies_at: [],
};
export const defaultMap: MapData = {
  center: { lat: 37.7749, lon: -122.4194 }, markers: [],
};
export const defaultHeat: HeatData = {
  label: 'ACTIVITY · 7×24', title: 'no data', total_hours: 0,
  grid: [], scale_min: 0, scale_max: 8,
};
export const defaultVideo: VideoData = {
  camera: 'CAM-04', status: 'OFFLINE', elapsed: '00:00:00',
  resolution: '1080p', fps: 30, progress: 0,
  elapsed_short: '00:00', remaining: '-00:00',
};
export const defaultVitals: VitalsData = { metrics: [] };
export const defaultCalendar: CalendarData = { events: [] };
export const defaultTasks: TasksData = { items: [] };
export const defaultAgentLog: AgentLogData = { lines: [] };
export const defaultVoice: VoiceData = { status: 'IDLE', transcript: '' };
export const defaultClock: ClockData = { zones: [] };
