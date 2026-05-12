<script lang="ts">
  export let size: number = 220;
</script>

<div style="position: relative; width: {size}px; height: {size}px;">
  <svg width={size} height={size} viewBox="0 0 100 100" style="position: absolute; inset: 0;">
    <defs>
      <radialGradient id="rsg">
        <stop offset="0%" stop-color="#b8d8ff" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="#b8d8ff" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="rbm" x1="50%" y1="50%" x2="100%" y2="50%">
        <stop offset="0%" stop-color="#b8d8ff" stop-opacity="0.45"/>
        <stop offset="100%" stop-color="#b8d8ff" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <circle cx="50" cy="50" r="48" fill="url(#rsg)"/>
    {#each [14, 28, 42] as r}
      <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(255,255,255,0.07)"/>
    {/each}
    <line x1="2" y1="50" x2="98" y2="50" stroke="rgba(255,255,255,0.04)"/>
    <line x1="50" y1="2" x2="50" y2="98" stroke="rgba(255,255,255,0.04)"/>
    <g class="sweep">
      <path d="M 50 50 L 98 50 A 48 48 0 0 0 80 14 Z" fill="url(#rbm)"/>
    </g>
    <circle cx="72" cy="38" r="0.9" fill="#b8d8ff"/>
    <circle cx="34" cy="60" r="0.9" fill="#b8d8ff"/>
    <circle cx="68" cy="72" r="0.9" fill="#b8d8ff"/>
  </svg>
</div>

<style>
  .sweep { transform-origin: 50px 50px; animation: spin 6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
