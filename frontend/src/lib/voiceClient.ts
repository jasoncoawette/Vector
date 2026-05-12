// Voice client: mic capture -> WebSocket -> TTS audio playback.
//
// Wire protocol (matches backend /voice/stream):
//   client -> server:
//     - binary frames: raw 16kHz PCM mic chunks
//     - JSON {type: "end"}      end this turn (mic stopped)
//     - JSON {type: "barge_in"} user started speaking mid-TTS
//   server -> client:
//     - binary frames: TTS audio chunks (audio/mpeg from ElevenLabs)
//     - JSON {kind: "state",      state: "listen"|"think"|"speak"|"idle"|"error"}
//     - JSON {kind: "transcript", text: "..."}
//     - JSON {kind: "reply",      text: "..."}
//     - JSON {kind: "bargein",    state: "listen"}
//     - JSON {kind: "error",      error: "...",       state: "error"}
//
// Browser limitations:
//   - getUserMedia delivers 48kHz Float32; we downsample + int16-pack here.
//   - MediaSource for streamed MP3 needs SourceBuffer; we just queue and
//     decode each chunk via decodeAudioData. It's simple, works in all
//     evergreens, latency-acceptable for <1MB clips.

import type { VoiceState } from './voiceState';

export type VoiceEventKind =
  | 'state'
  | 'transcript'
  | 'reply'
  | 'clarify'
  | 'bargein'
  | 'error';

export interface VoiceEvent {
  kind: VoiceEventKind;
  state?: VoiceState;
  text?: string;
  error?: string;
}

export interface VoiceClientOptions {
  url: string; // ws:// or wss:// URL, including ?token= if needed
  onEvent?: (e: VoiceEvent) => void;
  onAudio?: (chunk: ArrayBuffer) => void;
  onClose?: () => void;
}

const TARGET_RATE = 16_000;
const FRAME_MS = 100; // ship a 100ms PCM frame every ~100ms

export class VoiceClient {
  private ws: WebSocket | null = null;
  private audioCtx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private stream: MediaStream | null = null;
  private buffer: number[] = []; // Int16 samples queued for shipping
  private samplesPerFrame = 0;
  private playbackTime = 0;
  private playbackCtx: AudioContext | null = null;

  constructor(private opts: VoiceClientOptions) {}

  /** Open the WebSocket and wait for it to be ready. */
  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.opts.url);
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        this.ws = ws;
        resolve();
      };
      ws.onerror = (e) => {
        reject(new Error(`ws error: ${e}`));
      };
      ws.onmessage = (msg) => this.handleMessage(msg.data);
      ws.onclose = () => {
        this.opts.onClose?.();
        this.cleanup();
      };
    });
  }

  /** Start streaming mic input. Push-to-talk callers invoke this on press. */
  async startCapture(): Promise<void> {
    if (!this.ws) throw new Error('connect() first');
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.audioCtx = new AudioContext();
    this.samplesPerFrame = Math.floor((this.audioCtx.sampleRate * FRAME_MS) / 1000);
    this.source = this.audioCtx.createMediaStreamSource(this.stream);
    // ScriptProcessorNode is deprecated but works everywhere. AudioWorklet
    // is the long-term replacement; swap in later if latency matters.
    this.processor = this.audioCtx.createScriptProcessor(2048, 1, 1);
    this.processor.onaudioprocess = (e) => this.onAudioChunk(e.inputBuffer.getChannelData(0));
    this.source.connect(this.processor);
    this.processor.connect(this.audioCtx.destination);
  }

  /** Stop the mic and tell the backend this turn is done. */
  endTurn(): void {
    this.flushBuffer();
    this.stopMic();
    this.ws?.send(JSON.stringify({ type: 'end' }));
  }

  /** User started talking while TTS was speaking — cancel playback. */
  bargeIn(): void {
    this.ws?.send(JSON.stringify({ type: 'barge_in' }));
    this.playbackTime = 0;
    if (this.playbackCtx) {
      this.playbackCtx.close().catch(() => undefined);
      this.playbackCtx = null;
    }
  }

  close(): void {
    this.ws?.close();
    this.cleanup();
  }

  // --- private --------------------------------------------------------

  private onAudioChunk(samples: Float32Array): void {
    if (!this.audioCtx) return;
    // Downsample to TARGET_RATE by simple decimation. For 48kHz input
    // that's every 3rd sample; for 44.1kHz it's roughly every 2.76th.
    const ratio = this.audioCtx.sampleRate / TARGET_RATE;
    for (let i = 0; i < samples.length; i += ratio) {
      const idx = Math.floor(i);
      const v = Math.max(-1, Math.min(1, samples[idx] ?? 0));
      this.buffer.push(v < 0 ? v * 0x8000 : v * 0x7fff);
    }
    // Ship one frame's worth at a time.
    while (this.buffer.length >= this.samplesPerFrame) {
      this.shipFrame(this.buffer.splice(0, this.samplesPerFrame));
    }
  }

  private shipFrame(samples: number[]): void {
    const buf = new ArrayBuffer(samples.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < samples.length; i++) {
      view.setInt16(i * 2, samples[i] | 0, true);
    }
    this.ws?.send(buf);
  }

  private flushBuffer(): void {
    if (this.buffer.length > 0) {
      this.shipFrame(this.buffer);
      this.buffer = [];
    }
  }

  private async handleMessage(data: ArrayBuffer | string): Promise<void> {
    if (typeof data === 'string') {
      try {
        const event = JSON.parse(data) as VoiceEvent;
        this.opts.onEvent?.(event);
      } catch {
        // Ignore malformed frames.
      }
      return;
    }
    // Binary frame: TTS audio chunk.
    this.opts.onAudio?.(data);
    await this.playAudioChunk(data);
  }

  private async playAudioChunk(chunk: ArrayBuffer): Promise<void> {
    if (!this.playbackCtx) {
      this.playbackCtx = new AudioContext();
      this.playbackTime = this.playbackCtx.currentTime;
    }
    try {
      const decoded = await this.playbackCtx.decodeAudioData(chunk.slice(0));
      const src = this.playbackCtx.createBufferSource();
      src.buffer = decoded;
      src.connect(this.playbackCtx.destination);
      const start = Math.max(this.playbackTime, this.playbackCtx.currentTime);
      src.start(start);
      this.playbackTime = start + decoded.duration;
    } catch {
      // ElevenLabs sometimes ships chunks that aren't standalone-decodable
      // (mid-frame split). Drop silently — chained queue keeps audio
      // running and the next chunk will sync up.
    }
  }

  private stopMic(): void {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioCtx?.close().catch(() => undefined);
    this.processor = null;
    this.source = null;
    this.stream = null;
    this.audioCtx = null;
  }

  private cleanup(): void {
    this.stopMic();
    if (this.playbackCtx) {
      this.playbackCtx.close().catch(() => undefined);
      this.playbackCtx = null;
    }
    this.ws = null;
  }
}

export function buildVoiceUrl(backend: string, token: string | null): string {
  // Resolve relative or http(s) backend to ws(s).
  let base: string;
  if (backend === '') {
    if (typeof window === 'undefined') {
      throw new Error('cannot resolve voice URL without backend or window');
    }
    base = window.location.origin;
  } else {
    base = backend;
  }
  const url = new URL('/voice/stream', base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (token) url.searchParams.set('token', token);
  return url.toString();
}
