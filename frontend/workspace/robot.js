/**
 * NEXUS companion — a friendly 3D robot rendered with the vendored three.js build.
 *
 * No external assets: every mesh is procedural, so the hero bubble stays crisp at
 * any DPI and costs ~35 draw calls. The renderer pauses when the stage leaves the
 * viewport (or the tab is hidden) and falls back to the inline SVG robot when WebGL
 * is unavailable. `window.NexusRobot` exposes `react()` / `setMood()` for the console
 * to drive reactions while a run streams.
 */

import * as THREE from '../vendor/three.module.js';

const CYAN = 0x22d3ee;
const VIOLET = 0x8b5cf6;
const ORANGE = 0xff7a18;
const INK = 0x0b0f19;

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
const rand = (min, max) => min + Math.random() * (max - min);

function roundedRectShape(width, height, radius) {
  const w = width / 2;
  const h = height / 2;
  const r = Math.min(radius, Math.min(w, h));
  const shape = new THREE.Shape();
  shape.moveTo(-w + r, -h);
  shape.lineTo(w - r, -h);
  shape.quadraticCurveTo(w, -h, w, -h + r);
  shape.lineTo(w, h - r);
  shape.quadraticCurveTo(w, h, w - r, h);
  shape.lineTo(-w + r, h);
  shape.quadraticCurveTo(-w, h, -w, h - r);
  shape.lineTo(-w, -h + r);
  shape.quadraticCurveTo(-w, -h, -w + r, -h);
  return shape;
}

function softShadowTexture() {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, 'rgba(11,15,25,0.30)');
  gradient.addColorStop(0.55, 'rgba(11,15,25,0.10)');
  gradient.addColorStop(1, 'rgba(11,15,25,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function mountRobot(stage, canvas) {
  if (!stage || !canvas) return null;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
  } catch (error) {
    stage.dataset.webgl = 'off';
    return null;
  }
  if (!renderer || !renderer.getContext()) {
    stage.dataset.webgl = 'off';
    return null;
  }

  stage.dataset.webgl = 'on';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(33, 1, 0.1, 60);
  camera.position.set(0, 1.28, 5.5);
  camera.lookAt(0, 1.06, 0);

  // ── materials ────────────────────────────────────────────────────────────
  const porcelain = new THREE.MeshPhysicalMaterial({
    color: 0xf7f8fa, roughness: 0.36, metalness: 0.03, clearcoat: 1, clearcoatRoughness: 0.28,
    sheen: 0.35, sheenColor: new THREE.Color(0xdff7ff),
  });
  const porcelainWarm = new THREE.MeshPhysicalMaterial({
    color: 0xf1f3f7, roughness: 0.44, metalness: 0.02, clearcoat: 0.7, clearcoatRoughness: 0.4,
  });
  const graphite = new THREE.MeshPhysicalMaterial({
    color: INK, roughness: 0.16, metalness: 0.42, clearcoat: 1, clearcoatRoughness: 0.12,
  });
  const orangeMat = new THREE.MeshStandardMaterial({
    color: ORANGE, roughness: 0.34, metalness: 0.12, emissive: 0xff4d00, emissiveIntensity: 0.18,
  });
  const glowCyan = new THREE.MeshBasicMaterial({ color: 0x9df6ff, toneMapped: false });
  const glowWarm = new THREE.MeshBasicMaterial({ color: 0xffc38a, toneMapped: false });
  const ringCyan = new THREE.MeshBasicMaterial({
    color: CYAN, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false,
  });
  const ringViolet = new THREE.MeshBasicMaterial({
    color: VIOLET, transparent: true, opacity: 0.36, blending: THREE.AdditiveBlending, depthWrite: false,
  });

  // ── lighting (soft studio key + cyan/violet rim) ─────────────────────────
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd8dde6, 2.1));

  const key = new THREE.DirectionalLight(0xffffff, 3.1);
  key.position.set(2.6, 5.2, 4.2);
  scene.add(key);

  const rimCyan = new THREE.PointLight(CYAN, 16, 9, 2);
  rimCyan.position.set(-3.1, 2.4, 2.1);
  scene.add(rimCyan);

  const rimViolet = new THREE.PointLight(VIOLET, 13, 9, 2);
  rimViolet.position.set(3.2, 1.1, -1.6);
  scene.add(rimViolet);

  const fill = new THREE.DirectionalLight(0xfff4ea, 1.15);
  fill.position.set(-2.4, 1.6, 3.4);
  scene.add(fill);

  // ── robot ────────────────────────────────────────────────────────────────
  const robot = new THREE.Group();
  scene.add(robot);

  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(2.5, 1.05),
    new THREE.MeshBasicMaterial({ map: softShadowTexture(), transparent: true, depthWrite: false }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -0.12;
  scene.add(shadow);

  // hover rings
  const hover = new THREE.Group();
  hover.position.y = 0.02;
  const ringA = new THREE.Mesh(new THREE.TorusGeometry(0.66, 0.012, 8, 96), ringCyan);
  ringA.rotation.x = Math.PI / 2;
  const ringB = new THREE.Mesh(new THREE.TorusGeometry(0.84, 0.009, 8, 96), ringViolet);
  ringB.rotation.x = Math.PI / 2;
  hover.add(ringA, ringB);
  robot.add(hover);

  // body
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.5, 0.3, 24, 40), porcelain);
  body.position.y = 0.68;
  robot.add(body);

  const belly = new THREE.Mesh(new THREE.CircleGeometry(0.225, 40), porcelainWarm);
  belly.position.set(0, 0.62, 0.483);
  belly.scale.y = 0.86;
  robot.add(belly);

  const core = new THREE.Mesh(new THREE.TorusGeometry(0.085, 0.016, 12, 40), graphite);
  core.position.set(0, 0.7, 0.51);
  robot.add(core);
  const coreDot = new THREE.Mesh(new THREE.CircleGeometry(0.05, 24), glowCyan);
  coreDot.position.set(0, 0.7, 0.516);
  robot.add(coreDot);

  // shoulders / arms
  const arms = [];
  [-1, 1].forEach((side) => {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.52, 0.96, 0);
    const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.1, 0.24, 16, 24), porcelainWarm);
    arm.position.set(side * 0.09, -0.24, 0);
    arm.rotation.z = side * 0.28;
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.115, 26, 22), porcelain);
    hand.position.set(side * 0.19, -0.47, 0.02);
    pivot.add(arm, hand);
    pivot.rotation.z = side * -0.12;
    robot.add(pivot);
    arms.push({ pivot, side });
  });

  // neck
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.17, 0.18, 24), graphite);
  neck.position.y = 1.2;
  robot.add(neck);

  // head group (tilts / nods)
  const head = new THREE.Group();
  head.position.y = 1.72;
  robot.add(head);

  const skull = new THREE.Mesh(new THREE.SphereGeometry(0.57, 64, 56), porcelain);
  skull.scale.set(1, 0.93, 0.97);
  head.add(skull);

  // faceplate
  const faceGeo = new THREE.ExtrudeGeometry(roundedRectShape(0.64, 0.46, 0.2), {
    depth: 0.1, bevelEnabled: true, bevelSize: 0.05, bevelThickness: 0.045, bevelSegments: 6, curveSegments: 26,
  });
  faceGeo.center();
  const face = new THREE.Mesh(faceGeo, graphite);
  face.position.set(0, -0.01, 0.47);
  face.scale.set(1, 1, 0.9);
  head.add(face);

  // eyes (blink by scaling on Y)
  const eyes = new THREE.Group();
  eyes.position.set(0, 0.02, 0.578);
  head.add(eyes);
  const eyeMeshes = [];
  [-1, 1].forEach((side) => {
    const socket = new THREE.Mesh(new THREE.CircleGeometry(0.055, 26), glowCyan);
    socket.position.set(side * 0.135, 0.032, 0);
    const pupil = new THREE.Mesh(new THREE.CircleGeometry(0.025, 20), new THREE.MeshBasicMaterial({ color: 0x0b0f19 }));
    pupil.position.set(side * 0.135, 0.032, 0.004);
    eyes.add(socket, pupil);
    eyeMeshes.push(socket);
  });

  // smile
  const smile = new THREE.Mesh(
    new THREE.TorusGeometry(0.058, 0.01, 10, 30, Math.PI),
    new THREE.MeshBasicMaterial({ color: 0x67e8f9 }),
  );
  smile.position.set(0, -0.062, 0.58);
  smile.rotation.z = Math.PI;
  head.add(smile);

  // ear pods
  [-1, 1].forEach((side) => {
    const pod = new THREE.Mesh(new THREE.CylinderGeometry(0.128, 0.128, 0.1, 30), orangeMat);
    pod.rotation.z = Math.PI / 2;
    pod.position.set(side * 0.545, -0.02, 0.02);
    const cap = new THREE.Mesh(new THREE.CircleGeometry(0.058, 24), glowWarm);
    cap.position.set(side * 0.598, -0.02, 0.02);
    cap.rotation.y = side * (Math.PI / 2);
    head.add(pod, cap);
  });

  // antenna
  const antenna = new THREE.Group();
  antenna.position.set(0, 0.48, 0);
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.018, 0.28, 12), graphite);
  stem.position.y = 0.14;
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.062, 24, 20), orangeMat);
  bulb.position.y = 0.3;
  const bulbHalo = new THREE.Mesh(
    new THREE.SphereGeometry(0.1, 20, 16),
    new THREE.MeshBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.16, depthWrite: false }),
  );
  bulbHalo.position.y = 0.3;
  antenna.add(stem, bulb, bulbHalo);
  head.add(antenna);

  // ── ambient motes ────────────────────────────────────────────────────────
  const count = 46;
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const angle = Math.random() * Math.PI * 2;
    const radius = rand(1.0, 1.85);
    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = rand(0.15, 2.5);
    positions[i * 3 + 2] = Math.sin(angle) * radius * 0.6 - 0.4;
    seeds[i * 3] = rand(0, Math.PI * 2);
    seeds[i * 3 + 1] = rand(0.4, 1.2);
    seeds[i * 3 + 2] = rand(0.4, 1.4);
  }
  const moteGeo = new THREE.BufferGeometry();
  moteGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const motes = new THREE.Points(
    moteGeo,
    new THREE.PointsMaterial({
      color: 0x8fe9f7, size: 0.028, transparent: true, opacity: 0.6,
      depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true,
    }),
  );
  scene.add(motes);

  // ── state ────────────────────────────────────────────────────────────────
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  let blinkAt = performance.now() + rand(1400, 3200);
  let blinkProgress = -1;
  let mood = 'idle';
  let moodUntil = 0;
  let bounce = 0;
  let running = true;
  let last = performance.now();

  const onPointerMove = (event) => {
    const rect = stage.getBoundingClientRect();
    pointer.tx = clamp(((event.clientX - rect.left) / rect.width) * 2 - 1, -1, 1);
    pointer.ty = clamp(((event.clientY - rect.top) / rect.height) * 2 - 1, -1, 1);
  };
  const onPointerLeave = () => {
    pointer.tx = 0;
    pointer.ty = 0;
  };
  stage.addEventListener('pointermove', onPointerMove);
  stage.addEventListener('pointerleave', onPointerLeave);
  stage.addEventListener('pointerdown', () => {
    bounce = 1;
    react('talk', 900);
  });

  function resize() {
    const width = stage.clientWidth || 320;
    const height = stage.clientHeight || 260;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = width / height < 1 ? 40 : width / height < 1.6 ? 36 : 32;
    camera.updateProjectionMatrix();
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  resize();

  const visibility = new IntersectionObserver(
    (entries) => {
      running = entries[0]?.isIntersecting ?? true;
      if (running) last = performance.now();
    },
    { threshold: 0.05 },
  );
  visibility.observe(stage);

  const onVisibility = () => {
    if (!document.hidden) last = performance.now();
  };
  document.addEventListener('visibilitychange', onVisibility);

  function react(kind = 'talk', duration = 1600) {
    mood = kind;
    moodUntil = performance.now() + duration;
  }

  function animate(now) {
    requestAnimationFrame(animate);
    if (!running || document.hidden) return;
    const delta = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = now / 1000;
    if (now > moodUntil) mood = 'idle';
    const active = mood === 'talk';
    const amp = reduceMotion ? 0.25 : 1;

    pointer.x += (pointer.tx - pointer.x) * 0.06;
    pointer.y += (pointer.ty - pointer.y) * 0.06;

    // float + reveal bounce
    bounce = Math.max(0, bounce - delta * 2.6);
    const bounceY = Math.sin(bounce * Math.PI) * 0.12;
    robot.position.y = Math.sin(t * 0.9) * 0.045 * amp + bounceY;
    robot.rotation.y = Math.sin(t * 0.32) * 0.14 * amp + pointer.x * 0.34;
    robot.rotation.x = pointer.y * 0.05;

    // head look + nod
    head.rotation.y = pointer.x * 0.2 + Math.sin(t * 0.42) * 0.05 * amp;
    head.rotation.x = pointer.y * 0.12 + (active ? Math.sin(t * 9) * 0.035 : Math.sin(t * 0.8) * 0.02);
    head.rotation.z = Math.sin(t * 0.55) * 0.03 * amp;

    // arms
    arms.forEach(({ pivot, side }, index) => {
      const swing = active ? Math.sin(t * 7 + index) * 0.22 : Math.sin(t * 1.1 + index * 0.6) * 0.06;
      pivot.rotation.z = side * -0.12 + swing * side;
      pivot.rotation.x = active ? Math.sin(t * 5 + index) * 0.1 : 0;
    });

    // antenna sway
    antenna.rotation.z = Math.sin(t * 1.7) * 0.1 * amp + (active ? Math.sin(t * 8) * 0.06 : 0);
    bulbHalo.scale.setScalar(1 + Math.sin(t * 2.4) * 0.12 + (active ? 0.18 : 0));

    // core pulse
    const pulse = 0.85 + Math.sin(t * 2.2) * 0.15 + (active ? 0.15 : 0);
    coreDot.scale.setScalar(pulse);
    coreDot.material.color.setHex(active ? 0xd8fbff : 0x9df6ff);

    // hover rings
    hover.rotation.y = t * 0.35;
    ringA.rotation.z = t * 0.4;
    ringB.rotation.z = -t * 0.24;
    ringA.material.opacity = 0.32 + Math.sin(t * 1.6) * 0.12 + (active ? 0.16 : 0);
    ringB.material.opacity = 0.22 + Math.sin(t * 1.1 + 1.5) * 0.1;

    // blink
    if (blinkProgress < 0 && now > blinkAt) blinkProgress = 0;
    if (blinkProgress >= 0) {
      blinkProgress += delta * 5.2;
      const closed = blinkProgress < 0.5 ? 1 - blinkProgress * 2 : (blinkProgress - 0.5) * 2;
      eyeMeshes.forEach((eye) => { eye.scale.y = clamp(closed, 0.08, 1); });
      if (blinkProgress >= 1) {
        blinkProgress = -1;
        blinkAt = now + rand(2600, 6400);
        eyeMeshes.forEach((eye) => { eye.scale.y = 1; });
      }
    }
    eyes.scale.x = 1 + (active ? Math.sin(t * 10) * 0.02 : 0);
    smile.scale.x = 1 + (active ? 0.12 : 0);

    // motes drift
    const attr = moteGeo.getAttribute('position');
    for (let i = 0; i < count; i += 1) {
      const phase = seeds[i * 3];
      attr.array[i * 3 + 1] = positions[i * 3 + 1] + Math.sin(t * seeds[i * 3 + 1] + phase) * 0.13;
      attr.array[i * 3] = positions[i * 3] + Math.cos(t * 0.22 + phase) * 0.07;
    }
    attr.needsUpdate = true;
    motes.rotation.y = t * 0.04;

    // rim lights breathe
    rimCyan.intensity = 13 + Math.sin(t * 1.4) * 3 + (active ? 4 : 0);
    rimViolet.intensity = 11 + Math.cos(t * 1.1) * 2.5;

    renderer.render(scene, camera);
  }
  requestAnimationFrame(animate);

  const api = {
    react,
    setMood: (value) => react(value, value === 'talk' ? 2000 : 400),
    dispose() {
      running = false;
      resizeObserver.disconnect();
      visibility.disconnect();
      stage.removeEventListener('pointermove', onPointerMove);
      stage.removeEventListener('pointerleave', onPointerLeave);
      document.removeEventListener('visibilitychange', onVisibility);
      scene.traverse((object) => {
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => {
            if (material.map) material.map.dispose();
            material.dispose();
          });
        }
      });
      renderer.dispose();
    },
  };
  window.NexusRobot = api;
  return api;
}

export function bootRobot() {
  const stage = document.getElementById('robot-stage');
  const canvas = document.getElementById('robot-canvas');
  if (!stage || !canvas) return null;
  if (!window.WebGLRenderingContext) {
    stage.dataset.webgl = 'off';
    return null;
  }
  try {
    return mountRobot(stage, canvas);
  } catch (error) {
    console.warn('[nexus] robot renderer unavailable, using SVG fallback', error);
    stage.dataset.webgl = 'off';
    return null;
  }
}
