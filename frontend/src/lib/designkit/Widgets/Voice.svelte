<script lang="ts">
  import Waveform from '../Charts/Waveform.svelte';
  import type { VoiceData } from '../api';

  export let data: VoiceData | null = null;

  $: status = data?.status ?? 'LISTENING · 0:14';
  $: transcript = data?.transcript ?? 'remind me to follow up with the architect about the kitchen...';
</script>

<div class="wrap">
  <div class="head">
    <div class="orb-wrap">
      <span class="halo"></span>
      <span class="orb"></span>
    </div>
    <span class="mono status">{status}</span>
  </div>
  <Waveform w={300} h={36}/>
  <div class="mono cap">"{transcript}"</div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; justify-content: space-between; height: 100%; }
  .head { display: flex; align-items: center; gap: 12px; }
  .orb-wrap { position: relative; width: 36px; height: 36px; flex-shrink: 0; }
  .halo {
    position: absolute; inset: 0; border-radius: 99px; background: var(--vec);
    opacity: 0.16; animation: pulse 2s ease-out infinite;
  }
  .orb {
    position: absolute; inset: 8px; border-radius: 99px; background: var(--vec);
  }
  .status { font-size: 11px; color: var(--ink-2); letter-spacing: 0.16em; }
  .cap { font-size: 12px; color: var(--ink-1); margin-top: 4px; }
  @keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 0.6; }
    50%      { transform: scale(1.4); opacity: 0; }
  }
</style>
