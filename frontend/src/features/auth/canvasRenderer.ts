import { FLOW_HEIGHT, FLOW_WIDTH, flattenWave, ribbonFrame, ribbonPath, type Point, type WaveFrame } from "./ribbonGeometry";
export type SceneMapping = { scale: number; x: number; y: number };
export type ParticleFrame = { x: number; y: number; radius: number; opacity: number };
export type AuroraRenderer = { resize: (width: number, height: number, dpr: number) => void; render: (seconds: number, updateLights?: boolean) => void; destroy: () => void };
const PARTICLES = [
  [.08,.18,1,.28,12,-24,8,2], [.14,.28,1.5,.22,-18,32,7,5],
  [.09,.68,2,.18,24,-40,10,3], [.22,.88,1.5,.30,-10,18,6,4],
  [.92,.22,1.5,.36,-18,32,9,6], [.86,.38,1,.26,12,-24,7,3],
  [.94,.64,2,.20,-10,18,10,7], [.88,.83,1.5,.32,24,-40,9,2],
  [.62,.08,1,.24,-18,32,6,1], [.55,.92,1.5,.28,12,-24,8,5],
];
export function sceneMapping(width: number, height: number): SceneMapping {
  const scale = Math.max(width / FLOW_WIDTH, height / FLOW_HEIGHT);
  return { scale, x: (width - FLOW_WIDTH * scale) / 2, y: (height - FLOW_HEIGHT * scale) / 2 };
}
export function cssToWorld(x: number, y: number, mapping: SceneMapping): Point { return [(x - mapping.x) / mapping.scale, (y - mapping.y) / mapping.scale]; }
// CSS ease-in-out cubic-bezier(.42,0,.58,1), alternate, original negative delays.
function ease(t: number): number {
  let low = 0, high = 1;
  for (let i = 0; i < 16; i++) {
    const m = (low + high) / 2, q = 1 - m;
    if (3 * q * q * m * .42 + 3 * q * m * m * .58 + m ** 3 < t) low = m; else high = m;
  }
  const m = (low + high) / 2;
  return 3 * (1 - m) * m * m + m ** 3;
}
export function particleFrames(seconds: number, width: number, height: number): ParticleFrame[] {
  return PARTICLES.map(([x,y,radius,opacity,dx,dy,duration,delay]) => {
    const phase = ((seconds + delay) / duration) % 2, drift = ease(phase <= 1 ? phase : 2 - phase);
    return { x: x * width + radius + dx * drift, y: y * height + radius + dy * drift, radius, opacity };
  });
}
// Each segment stores ax, ay, dx, dy, length² and its expanded AABB. These
// values only change with the light path (30 Hz), not with every particle frame.
const SEGMENT_STRIDE = 9;
const INNER_RADII = [40, 52] as const;
const OUTER_RADII = [48, 60] as const;
// A tiny margin avoids rejecting a segment at an exactly rounded boundary.
const BOUNDS_MARGIN = 1e-9;
type CoveredWave = { minX: number; minY: number; maxX: number; maxY: number; segments: Float64Array };
export type WaveCoverage = readonly CoveredWave[];
export function waveCoverage(waves: readonly WaveFrame[]): WaveCoverage {
  return waves.filter(wave => wave.index < 2).map((wave, index) => {
    const points = flattenWave(wave), outer = OUTER_RADII[index] + BOUNDS_MARGIN;
    const segments = new Float64Array((points.length - 1) * SEGMENT_STRIDE);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i], dx = b[0] - a[0], dy = b[1] - a[1];
      const left = Math.min(a[0], b[0]) - outer, right = Math.max(a[0], b[0]) + outer;
      const top = Math.min(a[1], b[1]) - outer, bottom = Math.max(a[1], b[1]) + outer;
      const offset = (i - 1) * SEGMENT_STRIDE;
      segments[offset] = a[0]; segments[offset + 1] = a[1];
      segments[offset + 2] = dx; segments[offset + 3] = dy; segments[offset + 4] = dx * dx + dy * dy;
      segments[offset + 5] = left; segments[offset + 6] = top; segments[offset + 7] = right; segments[offset + 8] = bottom;
      minX = Math.min(minX, left); minY = Math.min(minY, top);
      maxX = Math.max(maxX, right); maxY = Math.max(maxY, bottom);
    }
    return { minX, minY, maxX, maxY, segments };
  });
}
export function particleVisibility(point: Point, waves: WaveCoverage): number {
  let visibility = 1;
  for (let index = 0; index < waves.length; index++) {
    const wave = waves[index], x = point[0], y = point[1];
    if (x < wave.minX || x > wave.maxX || y < wave.minY || y > wave.maxY) continue;
    const inner = INNER_RADII[index], outer = OUTER_RADII[index];
    const innerSafe = (inner - BOUNDS_MARGIN) ** 2, outerSafe = (outer + BOUNDS_MARGIN) ** 2;
    let distance = Infinity;
    for (let i = 0; i < wave.segments.length; i += SEGMENT_STRIDE) {
      const s = wave.segments;
      if (x < s[i + 5] || y < s[i + 6] || x > s[i + 7] || y > s[i + 8]) continue;
      const ax = s[i], ay = s[i + 1], dx = s[i + 2], dy = s[i + 3], length = s[i + 4];
      const t = length ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / length)) : 0;
      const rx = x - ax - t * dx, ry = y - ay - t * dy, squared = rx * rx + ry * ry;
      if (squared < innerSafe) return 0;
      // Use the original hypot calculation in the fade zone, preserving opacity.
      if (squared <= outerSafe) distance = Math.min(distance, Math.hypot(rx, ry));
    }
    const edge = Math.max(0, Math.min(1, (distance - inner) / 8));
    visibility = Math.min(visibility, edge * edge * (3 - 2 * edge));
  }
  return visibility;
}
export function createParticleSprite(): HTMLCanvasElement {
  const sprite = document.createElement("canvas"); sprite.width = sprite.height = 32;
  const context = sprite.getContext("2d");
  if (context) {
    // CSS circle uses the farthest corner as radius, so preserve that exact footprint.
    const glow = context.createRadialGradient(16,16,0,16,16,16 * Math.SQRT2);
    glow.addColorStop(0,"#c3f9f1"); glow.addColorStop(.24,"rgba(157,233,229,.6)");
    glow.addColorStop(.52,"rgba(112,211,215,.2)"); glow.addColorStop(.75,"rgba(112,211,215,0)");
    context.fillStyle = glow; context.fillRect(0,0,32,32);
  }
  return sprite;
}
export function paintParticles(context: CanvasRenderingContext2D, particles: readonly ParticleFrame[], mapping: SceneMapping, waves: WaveCoverage, sprite: CanvasImageSource): void {
  for (const particle of particles) {
    const visibility = particleVisibility(cssToWorld(particle.x,particle.y,mapping),waves);
    if (visibility <= 0) continue;
    context.globalAlpha = particle.opacity * visibility;
    const size = particle.radius * 2;
    context.drawImage(sprite,particle.x - particle.radius,particle.y - particle.radius,size,size);
  }
  context.globalAlpha = 1;
}
export function rasterSizes(width: number, height: number, dpr: number) {
  const scale = Math.min(Math.max(dpr,1),1.5,2400 / width,1800 / height);
  return { particleWidth: Math.max(1,Math.round(width * scale)), particleHeight: Math.max(1,Math.round(height * scale)) };
}
export function createAuroraRenderer(scene: HTMLDivElement): AuroraRenderer | null {
  const particles = scene.querySelector<HTMLCanvasElement>("canvas[data-aurora-particles]");
  const paths = [...scene.querySelectorAll<SVGPathElement>("[data-aurora-ribbon]")];
  const context = particles?.getContext("2d",{alpha:true});
  if (!particles || !context || paths.length !== 3) return null;
  let sprite: HTMLCanvasElement | null = null;
  let width = 1, height = 1, mapping = sceneMapping(1,1), particlesVisible = false;
  let waves = [ribbonFrame(0,0),ribbonFrame(1,0)], coverage: WaveCoverage = [];
  // Rectangles are stored in backing-store pixels, independent of later resize.
  // Clear every old sprite before painting the new frame, including overlaps.
  const dirty: number[] = [];
  const clearDirty = () => {
    if (!dirty.length) return;
    context.setTransform(1,0,0,1,0,0);
    for (let i = 0; i < dirty.length; i += 4) context.clearRect(dirty[i],dirty[i + 1],dirty[i + 2],dirty[i + 3]);
    dirty.length = 0;
  };
  return {
    resize(nextWidth,nextHeight,dpr) {
      width = Math.max(1,nextWidth); height = Math.max(1,nextHeight); mapping = sceneMapping(width,height);
      particlesVisible = window.innerWidth >= 1200 && window.innerHeight > 700;
      const sizes = particlesVisible ? rasterSizes(width,height,dpr) : { particleWidth: 1, particleHeight: 1 };
      if (particles.width !== sizes.particleWidth || particles.height !== sizes.particleHeight) {
        particles.width = sizes.particleWidth; particles.height = sizes.particleHeight;
        dirty.length = 0;
      } else {
        // Resize/show/hide can change the mapping without changing rounded DPR size.
        context.setTransform(1,0,0,1,0,0); context.clearRect(0,0,particles.width,particles.height);
        dirty.length = 0;
      }
      coverage = particlesVisible ? waveCoverage(waves) : [];
    },
    render(seconds,updateLights = true) {
      if (updateLights) {
        waves = [0,1].map(index => ribbonFrame(index,seconds));
        waves.forEach((wave,index) => paths[index].setAttribute("d",ribbonPath(wave)));
        if (particlesVisible) coverage = waveCoverage(waves);
      }
      if (!particlesVisible) return;
      const scaleX = particles.width / width, scaleY = particles.height / height;
      const frame = particleFrames(seconds,width,height);
      clearDirty();
      context.setTransform(scaleX,0,0,scaleY,0,0);
      sprite ??= createParticleSprite();
      paintParticles(context,frame,mapping,coverage,sprite);
      for (const particle of frame) {
        // Two backing pixels cover filtering and fractional-DPR rounding.
        const left = Math.max(0,Math.floor((particle.x - particle.radius) * scaleX) - 2);
        const top = Math.max(0,Math.floor((particle.y - particle.radius) * scaleY) - 2);
        const right = Math.min(particles.width,Math.ceil((particle.x + particle.radius) * scaleX) + 2);
        const bottom = Math.min(particles.height,Math.ceil((particle.y + particle.radius) * scaleY) + 2);
        if (right > left && bottom > top) dirty.push(left,top,right - left,bottom - top);
      }
    },
    destroy() { context.setTransform(1,0,0,1,0,0); context.clearRect(0,0,particles.width,particles.height); dirty.length = 0; },
  };
}
