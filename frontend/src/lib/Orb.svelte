<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import * as THREE from 'three';
  import { orbColor, voice } from './voiceState';
  import type { VoiceState } from './voiceState';

  export let compact = false;
  export let size: number | null = null;

  let wrap: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let renderer: THREE.WebGLRenderer | null = null;
  let scene: THREE.Scene;
  let camera: THREE.PerspectiveCamera;
  let shell: THREE.Mesh;
  let core: THREE.Mesh;
  let lattice: THREE.LineSegments;
  let halo: THREE.Mesh;
  let shellMat: THREE.ShaderMaterial;
  let coreMat: THREE.ShaderMaterial;
  let haloMat: THREE.ShaderMaterial;
  let latticeMat: THREE.LineBasicMaterial;
  let matcapTex: THREE.CanvasTexture;
  let frame = 0;
  let resize: ResizeObserver | null = null;
  let clock = new THREE.Clock();

  let currentState: VoiceState = 'idle';
  let currentColor = new THREE.Color(0xb8d8ff);
  let stateMix = 0;
  let intensity = 0;

  $: full = compact ? 128 : 360;
  $: pxSize = size ?? full;

  const unsubColor = orbColor.subscribe((c) => {
    currentColor = new THREE.Color(c);
  });
  const unsubState = voice.state.subscribe((s) => {
    currentState = s;
  });

  // Procedural chrome matcap: dark sphere with bright hot-spot, subtle
  // cool->warm gradient. No external asset; renders once on init.
  function makeMatcap(): THREE.CanvasTexture {
    const N = 256;
    const c = document.createElement('canvas');
    c.width = c.height = N;
    const ctx = c.getContext('2d')!;
    // base radial dark -> mid silver
    const base = ctx.createRadialGradient(N * 0.5, N * 0.55, 0, N * 0.5, N * 0.5, N * 0.5);
    base.addColorStop(0.0, '#dfe6ee');
    base.addColorStop(0.35, '#8a93a0');
    base.addColorStop(0.7, '#1e2127');
    base.addColorStop(1.0, '#050608');
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, N, N);
    // hot spec
    const spec = ctx.createRadialGradient(N * 0.38, N * 0.32, 0, N * 0.38, N * 0.32, N * 0.32);
    spec.addColorStop(0.0, 'rgba(255,255,255,1)');
    spec.addColorStop(0.4, 'rgba(255,255,255,0.25)');
    spec.addColorStop(1.0, 'rgba(255,255,255,0)');
    ctx.globalCompositeOperation = 'screen';
    ctx.fillStyle = spec;
    ctx.fillRect(0, 0, N, N);
    // cool fill light
    const cool = ctx.createRadialGradient(N * 0.7, N * 0.75, 0, N * 0.7, N * 0.75, N * 0.45);
    cool.addColorStop(0.0, 'rgba(120,170,220,0.45)');
    cool.addColorStop(1.0, 'rgba(120,170,220,0)');
    ctx.fillStyle = cool;
    ctx.fillRect(0, 0, N, N);
    ctx.globalCompositeOperation = 'source-over';
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  // Ashima/Gustavson simplex 3D noise (MIT). Used for fluid vertex
  // displacement and surface flow.
  const SIMPLEX = /* glsl */ `
    vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
    float snoise(vec3 v){
      const vec2 C = vec2(1.0/6.0, 1.0/3.0);
      const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
      vec3 i  = floor(v + dot(v, C.yyy));
      vec3 x0 = v - i + dot(i, C.xxx);
      vec3 g = step(x0.yzx, x0.xyz);
      vec3 l = 1.0 - g;
      vec3 i1 = min(g.xyz, l.zxy);
      vec3 i2 = max(g.xyz, l.zxy);
      vec3 x1 = x0 - i1 + C.xxx;
      vec3 x2 = x0 - i2 + C.yyy;
      vec3 x3 = x0 - D.yyy;
      i = mod289(i);
      vec4 p = permute(permute(permute(
                  i.z + vec4(0.0, i1.z, i2.z, 1.0))
                + i.y + vec4(0.0, i1.y, i2.y, 1.0))
                + i.x + vec4(0.0, i1.x, i2.x, 1.0));
      float n_ = 0.142857142857;
      vec3 ns = n_ * D.wyz - D.xzx;
      vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
      vec4 x_ = floor(j * ns.z);
      vec4 y_ = floor(j - 7.0 * x_);
      vec4 x = x_ *ns.x + ns.yyyy;
      vec4 y = y_ *ns.x + ns.yyyy;
      vec4 h = 1.0 - abs(x) - abs(y);
      vec4 b0 = vec4(x.xy, y.xy);
      vec4 b1 = vec4(x.zw, y.zw);
      vec4 s0 = floor(b0)*2.0 + 1.0;
      vec4 s1 = floor(b1)*2.0 + 1.0;
      vec4 sh = -step(h, vec4(0.0));
      vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
      vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
      vec3 p0 = vec3(a0.xy, h.x);
      vec3 p1 = vec3(a0.zw, h.y);
      vec3 p2 = vec3(a1.xy, h.z);
      vec3 p3 = vec3(a1.zw, h.w);
      vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
      p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
      vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
      m = m * m;
      return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
    }
  `;

  const SHELL_VERT = /* glsl */ `
    uniform float uTime;
    uniform float uAmp;
    uniform float uFlow;
    uniform float uRipple;
    varying vec3 vViewNormal;
    varying vec3 vWorldNormal;
    varying vec3 vViewPosition;
    varying float vDisp;
    ${SIMPLEX}
    void main() {
      vec3 p = position;
      float t = uTime * uFlow;
      // layered fbm-ish noise: macro shape + micro detail
      float n1 = snoise(p * 1.4 + vec3(t * 0.5, t * 0.35, -t * 0.4));
      float n2 = snoise(p * 3.1 + vec3(-t * 0.7, t * 0.6, t * 0.5)) * 0.5;
      float n3 = snoise(p * 7.0 + vec3(t * 1.1, -t * 0.9, t * 0.8)) * 0.22;
      float n  = n1 + n2 + n3;
      // speaking ripple — radial pulse from poles
      float rip = sin((p.y + t * 2.0) * 6.0) * uRipple;
      float disp = n * uAmp + rip;
      vec3 displaced = p + normal * disp;
      vDisp = disp;
      vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
      vViewPosition = -mv.xyz;
      vViewNormal = normalize(normalMatrix * normal);
      vWorldNormal = normalize(mat3(modelMatrix) * normal);
      gl_Position = projectionMatrix * mv;
    }
  `;

  const SHELL_FRAG = /* glsl */ `
    precision highp float;
    uniform sampler2D uMatcap;
    uniform vec3 uTint;
    uniform float uRimPow;
    uniform float uRimStr;
    uniform float uIridescence;
    varying vec3 vViewNormal;
    varying vec3 vViewPosition;
    varying vec3 vWorldNormal;
    varying float vDisp;
    void main() {
      vec3 V = normalize(vViewPosition);
      vec3 N = normalize(vViewNormal);
      // matcap UV from view-space normal
      vec3 r = reflect(-V, N);
      float m = 2.0 * sqrt(pow(r.x, 2.0) + pow(r.y, 2.0) + pow(r.z + 1.0, 2.0));
      vec2 uv = r.xy / m + 0.5;
      vec3 mat = texture2D(uMatcap, uv).rgb;
      // fresnel rim
      float f = pow(1.0 - max(dot(N, V), 0.0), uRimPow);
      // iridescent shift from displacement & angle
      vec3 irid = vec3(
        0.5 + 0.5 * sin(6.2831 * (vDisp * 1.5 + 0.0)),
        0.5 + 0.5 * sin(6.2831 * (vDisp * 1.5 + 0.33)),
        0.5 + 0.5 * sin(6.2831 * (vDisp * 1.5 + 0.66))
      );
      vec3 base = mat * (0.85 + 0.15 * uTint);
      base = mix(base, base * uTint * 1.4, 0.35);
      base += irid * uIridescence * f;
      base += uTint * f * uRimStr;
      // soft gamma
      base = pow(base, vec3(0.95));
      gl_FragColor = vec4(base, 1.0);
    }
  `;

  const CORE_VERT = /* glsl */ `
    uniform float uTime;
    uniform float uAmp;
    varying vec3 vN;
    varying float vF;
    ${SIMPLEX}
    void main() {
      vec3 p = position;
      float n = snoise(p * 2.0 + vec3(uTime * 0.6));
      vec3 d = p + normal * n * uAmp;
      vec4 mv = modelViewMatrix * vec4(d, 1.0);
      vN = normalize(normalMatrix * normal);
      vec3 V = normalize(-mv.xyz);
      vF = 1.0 - max(dot(vN, V), 0.0);
      gl_Position = projectionMatrix * mv;
    }
  `;

  const CORE_FRAG = /* glsl */ `
    precision highp float;
    uniform vec3 uTint;
    uniform float uPulse;
    varying float vF;
    void main() {
      float a = smoothstep(0.0, 1.0, vF);
      vec3 c = mix(uTint * 0.4, uTint, a);
      float alpha = (0.18 + 0.55 * a) * uPulse;
      gl_FragColor = vec4(c, alpha);
    }
  `;

  const HALO_VERT = /* glsl */ `
    varying vec3 vN;
    varying vec3 vV;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vN = normalize(normalMatrix * normal);
      vV = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv;
    }
  `;

  const HALO_FRAG = /* glsl */ `
    precision highp float;
    uniform vec3 uTint;
    uniform float uStrength;
    varying vec3 vN;
    varying vec3 vV;
    void main() {
      float f = pow(1.0 - max(dot(vN, vV), 0.0), 2.2);
      gl_FragColor = vec4(uTint, f * uStrength);
    }
  `;

  // Per-state visual profile. uAmp = vertex displacement amplitude,
  // uFlow = noise speed, uRipple = radial pulse, uIridescence = chroma,
  // uRimStr = rim brightness, coreAmp = inner mesh disp, corePulse =
  // inner glow strength, latticeAlpha = HUD wireframe opacity.
  type Profile = {
    amp: number; flow: number; ripple: number;
    iridescence: number; rim: number;
    coreAmp: number; corePulse: number; latticeAlpha: number;
    spin: number;
  };
  const PROFILES: Record<VoiceState, Profile> = {
    idle:   { amp: 0.05, flow: 0.18, ripple: 0.00, iridescence: 0.05, rim: 0.55, coreAmp: 0.04, corePulse: 0.55, latticeAlpha: 0.18, spin: 0.08 },
    listen: { amp: 0.09, flow: 0.45, ripple: 0.02, iridescence: 0.10, rim: 0.85, coreAmp: 0.07, corePulse: 0.85, latticeAlpha: 0.32, spin: 0.18 },
    think:  { amp: 0.14, flow: 1.15, ripple: 0.00, iridescence: 0.25, rim: 0.70, coreAmp: 0.11, corePulse: 0.70, latticeAlpha: 0.55, spin: 0.55 },
    speak:  { amp: 0.18, flow: 0.65, ripple: 0.06, iridescence: 0.18, rim: 1.10, coreAmp: 0.13, corePulse: 1.20, latticeAlpha: 0.42, spin: 0.28 },
    error:  { amp: 0.22, flow: 1.40, ripple: 0.10, iridescence: 0.35, rim: 1.30, coreAmp: 0.16, corePulse: 1.20, latticeAlpha: 0.60, spin: 0.65 }
  };

  function build() {
    renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, alpha: true, premultipliedAlpha: false,
      powerPreference: 'high-performance'
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(pxSize, pxSize, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.z = 3.4;

    matcapTex = makeMatcap();

    // outer fluid shell
    const shellGeo = new THREE.IcosahedronGeometry(1, 64);
    shellMat = new THREE.ShaderMaterial({
      vertexShader: SHELL_VERT,
      fragmentShader: SHELL_FRAG,
      uniforms: {
        uTime: { value: 0 },
        uAmp: { value: 0.05 },
        uFlow: { value: 0.2 },
        uRipple: { value: 0 },
        uMatcap: { value: matcapTex },
        uTint: { value: currentColor.clone() },
        uRimPow: { value: 2.4 },
        uRimStr: { value: 0.6 },
        uIridescence: { value: 0.08 }
      }
    });
    shell = new THREE.Mesh(shellGeo, shellMat);
    scene.add(shell);

    // inner glow core (front-faces, additive)
    const coreGeo = new THREE.IcosahedronGeometry(0.72, 24);
    coreMat = new THREE.ShaderMaterial({
      vertexShader: CORE_VERT,
      fragmentShader: CORE_FRAG,
      uniforms: {
        uTime: { value: 0 },
        uAmp: { value: 0.05 },
        uTint: { value: currentColor.clone() },
        uPulse: { value: 0.6 }
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });
    core = new THREE.Mesh(coreGeo, coreMat);
    scene.add(core);

    // HUD lattice wireframe — the gear/circuit feel of the reference
    const latGeo = new THREE.IcosahedronGeometry(1.03, 3);
    const edges = new THREE.EdgesGeometry(latGeo, 1);
    latticeMat = new THREE.LineBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.2,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    lattice = new THREE.LineSegments(edges, latticeMat);
    scene.add(lattice);

    // outer halo shell — fresnel-only sphere, large + faint
    const haloGeo = new THREE.SphereGeometry(1.35, 64, 64);
    haloMat = new THREE.ShaderMaterial({
      vertexShader: HALO_VERT,
      fragmentShader: HALO_FRAG,
      uniforms: {
        uTint: { value: currentColor.clone() },
        uStrength: { value: 0.55 }
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.BackSide
    });
    halo = new THREE.Mesh(haloGeo, haloMat);
    scene.add(halo);
  }

  function applyProfile(dt: number) {
    const p = PROFILES[currentState];
    // exponential smoothing toward target uniforms — keeps state
    // transitions buttery instead of snapping.
    const k = 1 - Math.exp(-dt * 4.0);
    const u = shellMat.uniforms;
    u.uAmp.value      += (p.amp        - u.uAmp.value) * k;
    u.uFlow.value     += (p.flow       - u.uFlow.value) * k;
    u.uRipple.value   += (p.ripple     - u.uRipple.value) * k;
    u.uIridescence.value += (p.iridescence - u.uIridescence.value) * k;
    u.uRimStr.value   += (p.rim        - u.uRimStr.value) * k;
    (u.uTint.value as THREE.Color).lerp(currentColor, k);

    const cu = coreMat.uniforms;
    cu.uAmp.value     += (p.coreAmp    - cu.uAmp.value) * k;
    cu.uPulse.value   += (p.corePulse  - cu.uPulse.value) * k;
    (cu.uTint.value as THREE.Color).lerp(currentColor, k);

    latticeMat.opacity += (p.latticeAlpha - latticeMat.opacity) * k;
    (latticeMat.color as THREE.Color).lerp(currentColor, k * 0.5);

    (haloMat.uniforms.uTint.value as THREE.Color).lerp(currentColor, k);
    haloMat.uniforms.uStrength.value += ((p.rim * 0.6) - haloMat.uniforms.uStrength.value) * k;

    intensity = p.spin;
  }

  function tick() {
    if (!renderer) return;
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;
    applyProfile(dt);
    shellMat.uniforms.uTime.value = t;
    coreMat.uniforms.uTime.value = t * 1.3;

    // gentle drift + state-driven spin
    shell.rotation.y += dt * (0.05 + intensity);
    shell.rotation.x = Math.sin(t * 0.25) * 0.12;
    core.rotation.y -= dt * (0.08 + intensity * 1.6);
    core.rotation.x = Math.cos(t * 0.35) * 0.18;
    lattice.rotation.y -= dt * (0.12 + intensity * 0.8);
    lattice.rotation.x = Math.sin(t * 0.5) * 0.25;
    lattice.rotation.z = t * 0.05;

    // subtle breathing scale (more pronounced when speaking)
    const breathe = 1.0 + Math.sin(t * (currentState === 'speak' ? 6.0 : 1.4))
                          * (currentState === 'speak' ? 0.025 : 0.008);
    shell.scale.setScalar(breathe);

    renderer.render(scene, camera);
    frame = requestAnimationFrame(tick);
  }

  function handleResize() {
    if (!renderer) return;
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    const s = Math.min(w, h);
    if (s > 0) renderer.setSize(s, s, false);
  }

  onMount(() => {
    build();
    resize = new ResizeObserver(handleResize);
    resize.observe(wrap);
    clock.start();
    tick();
  });

  onDestroy(() => {
    cancelAnimationFrame(frame);
    resize?.disconnect();
    unsubColor();
    unsubState();
    shell?.geometry.dispose();
    core?.geometry.dispose();
    lattice?.geometry.dispose();
    halo?.geometry.dispose();
    shellMat?.dispose();
    coreMat?.dispose();
    haloMat?.dispose();
    latticeMat?.dispose();
    matcapTex?.dispose();
    if (renderer) {
      renderer.dispose();
      renderer = null;
    }
  });

  function handleClick() {
    voice.toggleMute();
  }
  function handleKey(e: KeyboardEvent) {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      voice.toggleMute();
    }
  }
</script>

<div
  bind:this={wrap}
  class="orb"
  class:compact
  data-state={currentState}
  style="--orb-size: {pxSize}px"
  on:click={handleClick}
  on:keydown={handleKey}
  role="button"
  tabindex="0"
  aria-label="Vector orb — {currentState}"
  title={currentState}
>
  <canvas bind:this={canvas}></canvas>
  <span class="state-label mono">{currentState}</span>
</div>

<style>
  .orb {
    width: var(--orb-size);
    height: var(--orb-size);
    position: relative;
    display: grid;
    place-items: center;
    cursor: pointer;
    outline: none;
    transition:
      width 380ms cubic-bezier(0.32, 0.72, 0.18, 1),
      height 380ms cubic-bezier(0.32, 0.72, 0.18, 1),
      transform 380ms cubic-bezier(0.32, 0.72, 0.18, 1),
      filter 280ms ease;
    filter: drop-shadow(0 8px 28px rgba(184, 216, 255, 0.18));
  }
  .orb:focus-visible {
    filter:
      drop-shadow(0 0 0 2px rgba(184, 216, 255, 0.6))
      drop-shadow(0 8px 28px rgba(184, 216, 255, 0.25));
  }
  .orb.compact {
    position: fixed;
    right: 22px;
    bottom: 78px;
    z-index: 40;
    filter: drop-shadow(0 6px 22px rgba(184, 216, 255, 0.22));
  }
  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }
  .state-label {
    position: absolute;
    bottom: -18px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 9px;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.42);
    pointer-events: none;
    white-space: nowrap;
    opacity: 0.85;
    transition: opacity 200ms ease;
  }
  .orb.compact .state-label {
    bottom: -14px;
    font-size: 8px;
    opacity: 0.6;
  }
  .orb[data-state='error'] .state-label { color: rgba(217, 122, 122, 0.85); }
  .orb[data-state='speak'] .state-label { color: rgba(255, 255, 255, 0.78); }
  .orb[data-state='think'] .state-label { color: rgba(201, 187, 136, 0.78); }
  .orb[data-state='listen'] .state-label { color: rgba(111, 179, 138, 0.78); }
</style>
