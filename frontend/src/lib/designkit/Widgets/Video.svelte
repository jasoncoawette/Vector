<script lang="ts">
  import type { VideoData } from '../api';

  export let data: VideoData | null = null;

  $: status = data?.status ?? 'LIVE';
  $: camera = data?.camera ?? 'CAM-04';
  $: elapsed = data?.elapsed ?? '04:22:18';
  $: resolution = data?.resolution ?? '1080p';
  $: fps = data?.fps ?? 30;
  $: progress = data?.progress ?? 0.38;
  $: elapsedShort = data?.elapsed_short ?? '01:42';
  $: remaining = data?.remaining ?? '-02:48';
  $: progressPct = `${Math.round(progress * 100)}%`;
</script>

<div class="frame">
  <div class="bg"></div>
  <svg width="100%" height="100%" class="grid">
    <defs>
      <pattern id="vgp" width="14" height="14" patternUnits="userSpaceOnUse">
        <path d="M 14 0 L 0 0 0 14" fill="none" stroke="white" stroke-width="0.4"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#vgp)"/>
  </svg>
  <div class="tc mono">● {status} · {camera} · {elapsed}</div>
  <div class="tcR mono">{resolution} · {fps}fps</div>
  <div class="play">
    <div class="circle"><div class="tri"></div></div>
  </div>
  <div class="scrub">
    <div class="bar">
      <div class="fill" style="width: {progressPct};"></div>
      <div class="thumb" style="left: {progressPct};"></div>
    </div>
    <div class="times mono"><span>{elapsedShort}</span><span>{remaining}</span></div>
  </div>
</div>

<style>
  .frame {
    position: relative; width: 100%; height: 100%; border-radius: 8px; overflow: hidden;
    background: linear-gradient(135deg, #1a1f2a 0%, #0d1116 100%);
  }
  .bg {
    position: absolute; inset: 0;
    background:
      radial-gradient(ellipse at 30% 40%, rgba(184,216,255,0.18), transparent 50%),
      radial-gradient(ellipse at 70% 60%, rgba(184,216,255,0.08), transparent 60%),
      linear-gradient(180deg, #131720, #0a0b0d);
  }
  .grid { position: absolute; inset: 0; opacity: 0.16; }
  .tc { position: absolute; top: 10px; left: 12px; font-size: 10px; color: var(--vec); letter-spacing: 0.2em; }
  .tcR { position: absolute; top: 10px; right: 12px; font-size: 10px; color: var(--ink-3); }
  .play { position: absolute; inset: 0; display: grid; place-items: center; }
  .circle {
    width: 52px; height: 52px; border-radius: 99px; border: 1px solid rgba(255,255,255,0.4);
    display: grid; place-items: center; backdrop-filter: blur(4px);
  }
  .tri {
    width: 0; height: 0;
    border-left: 11px solid #fff;
    border-top: 7px solid transparent; border-bottom: 7px solid transparent;
    margin-left: 3px;
  }
  .scrub { position: absolute; left: 12px; right: 12px; bottom: 12px; }
  .bar { height: 3px; background: rgba(255,255,255,0.12); border-radius: 2px; position: relative; }
  .fill { height: 100%; background: var(--vec); border-radius: 2px; }
  .thumb {
    position: absolute; top: -3px;
    width: 9px; height: 9px; border-radius: 99px; background: var(--vec);
    transform: translateX(-50%);
  }
  .times { display: flex; justify-content: space-between; margin-top: 4px; font-size: 9px; color: var(--ink-3); }
</style>
