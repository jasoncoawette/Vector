<script lang="ts">
  export let size: number = 40;
  export let stroke: number = 1.5;
  export let accent: string = 'var(--vec)';
</script>

<svg width={size} height={size} viewBox="0 0 40 40" fill="none">
  <circle cx="20" cy="20" r="18" stroke="currentColor" stroke-opacity="0.18" stroke-width="1"/>
  <circle cx="20" cy="20" r="13" stroke={accent} stroke-opacity="0.45" stroke-width="1"/>
  <path d="M11 27 L20 11 L29 27"
    stroke="currentColor" stroke-width={stroke}
    stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="20" cy="11" r="1.6" fill={accent}/>
</svg>
