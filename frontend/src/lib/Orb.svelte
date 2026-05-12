<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import * as THREE from 'three';
  import { orbColor, voice } from './voiceState';

  let canvas: HTMLCanvasElement;
  let renderer: THREE.WebGLRenderer | null = null;
  let scene: THREE.Scene;
  let camera: THREE.PerspectiveCamera;
  let mesh: THREE.Mesh;
  let material: THREE.MeshStandardMaterial;
  let frame = 0;

  let currentColor = 0x3b82f6;
  const unsubColor = orbColor.subscribe((c) => {
    currentColor = c;
    if (material) material.color.setHex(c);
  });

  onMount(() => {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(320, 320, false);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = 3;

    const geo = new THREE.IcosahedronGeometry(1, 2);
    material = new THREE.MeshStandardMaterial({ color: currentColor, roughness: 0.4 });
    mesh = new THREE.Mesh(geo, material);
    scene.add(mesh);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 0.8);
    key.position.set(2, 2, 2);
    scene.add(key);

    const tick = () => {
      mesh.rotation.y += 0.005;
      renderer!.render(scene, camera);
      frame = requestAnimationFrame(tick);
    };
    tick();
  });

  onDestroy(() => {
    cancelAnimationFrame(frame);
    unsubColor();
    if (mesh) {
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
    if (renderer) {
      renderer.dispose();
      renderer = null;
    }
  });

  function handleClick() {
    voice.toggleMute();
  }
</script>

<canvas bind:this={canvas} on:click={handleClick} aria-label="Vector orb" role="button" tabindex="0" />

<style>
  canvas {
    width: 320px;
    height: 320px;
    cursor: pointer;
  }
</style>
