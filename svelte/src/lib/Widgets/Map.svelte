<script lang="ts">
  const markers: [number, number, string, string][] = [
    [120, 90, 'var(--vec)', 'HOME'],
    [200, 70, 'var(--ok)', 'OFFICE'],
    [260, 110, 'var(--warn)', 'GYM']
  ];
</script>

<div class="wrap">
  <svg width="100%" height="100%" viewBox="0 0 320 180" preserveAspectRatio="none">
    <defs>
      <pattern id="mp" width="16" height="16" patternUnits="userSpaceOnUse">
        <path d="M 16 0 L 0 0 0 16" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="0.5"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#mp)"/>
    <path d="M 0 110 Q 60 80 120 95 T 240 88 T 320 100 L 320 180 L 0 180 Z"
      fill="rgba(184,216,255,0.04)" stroke="rgba(184,216,255,0.18)" stroke-width="0.7"/>
    <path d="M 40 40 Q 100 30 160 50 T 280 60" fill="none"
      stroke="rgba(184,216,255,0.12)" stroke-width="0.5" stroke-dasharray="2 3"/>
    {#each markers as [x, y, c, l]}
      <circle cx={x} cy={y} r="10" fill={c} opacity="0.12"/>
      <circle cx={x} cy={y} r="3" fill={c}/>
      <text x={x + 8} y={y + 3} font-family="JetBrains Mono" font-size="7" fill="var(--ink-2)" letter-spacing="1.5">{l}</text>
    {/each}
  </svg>
  <div class="coord mono">37.7749° N · 122.4194° W</div>
</div>

<style>
  .wrap {
    position: relative; width: 100%; height: 100%; border-radius: 8px; overflow: hidden;
    background: var(--bg-2); border: 1px solid var(--hair);
  }
  .coord {
    position: absolute; top: 8px; left: 10px;
    font-size: 9px; color: var(--ink-3); letter-spacing: 0.18em;
  }
</style>
