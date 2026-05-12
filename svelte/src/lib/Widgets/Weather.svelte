<div class="wrap">
  <div class="top">
    <div>
      <div class="mono lbl">SAN FRANCISCO · CLEAR</div>
      <div class="temp">62°</div>
      <div class="meta">H 68° · L 54° · feels 60°</div>
    </div>
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="4" stroke="var(--vec)" stroke-width="1.3"/>
      {#each [0, 45, 90, 135, 180, 225, 270, 315] as a}
        {@const rad = (a * Math.PI) / 180}
        <line
          x1={12 + Math.cos(rad) * 7} y1={12 + Math.sin(rad) * 7}
          x2={12 + Math.cos(rad) * 9.5} y2={12 + Math.sin(rad) * 9.5}
          stroke="var(--vec)" stroke-width="1.2" opacity="0.7"
        />
      {/each}
    </svg>
  </div>
  <div class="hours">
    {#each [['NOW', 62], ['11a', 64], ['1p', 67], ['3p', 67], ['5p', 64], ['7p', 59]] as [t, d]}
      <div class="hr">
        <div class="mono ht">{t}</div>
        <div class="hd">{d}°</div>
      </div>
    {/each}
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; justify-content: space-between; height: 100%; }
  .top { display: flex; justify-content: space-between; align-items: flex-start; }
  .lbl { font-size: 9px; color: var(--ink-3); letter-spacing: 0.22em; }
  .temp { font-size: 48px; font-weight: 300; letter-spacing: -0.03em; margin-top: 2px; line-height: 1; }
  .meta { font-size: 12px; color: var(--ink-2); margin-top: 4px; }
  .hours { display: flex; justify-content: space-between; gap: 4px; }
  .hr { text-align: center; flex: 1; }
  .ht { font-size: 9px; color: var(--ink-3); letter-spacing: 0.16em; }
  .hd { font-size: 13px; color: var(--ink-1); margin-top: 4px; }
</style>
