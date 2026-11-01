export type Point = readonly [number, number];
export type Cubic = readonly [Point, Point, Point, Point];
export type WaveFrame = { index: number; cubics: readonly Cubic[] };
export const FLOW_WIDTH = 1200;
export const FLOW_HEIGHT = 1000;
export const CONTROL_DISPLACEMENT_LIMITS = [32, 24, 0] as const;
const SOURCES = [
  [[-180, 1140], [90, 1030], [480, 760], [590, 470], [870, -20], [910, -260]],
  [[220, 1260], [360, 960], [710, 720], [1000, 625], [1380, 500], [1500, 320]],
  [[-280, 340], [60, 640], [460, 540], [720, 190], [1170, -80], [1510, 160]],
];
const PHASES = [.4, 2.6, 4.9], AMPLITUDES = [12, 62, 86, 58, 78, 14];
function originalPoints(index: number): Point[] {
  return SOURCES[index].map(([x, y], point) => {
    const phase = PHASES[index] + point * .83, amplitude = AMPLITUDES[point];
    return [x + Math.sin(phase) * amplitude * .7 + Math.sin(phase * 1.7) * amplitude * .22,
      y + Math.sin(phase * 1.2) * amplitude + Math.cos(phase) * amplitude * .27];
  });
}
function cubics(points: readonly Point[]): readonly Cubic[] {
  return [[points[0], points[1], points[2], points[3]], [points[3],
    [2 * points[3][0] - points[2][0], 2 * points[3][1] - points[2][1]], points[4], points[5]]];
}
const START = [0, 1, 2].map(originalPoints);
const BASE = START.map(points => points.map(point => point.map(value => Number(value.toFixed(2))) as unknown as Point));
function seededUnit(seed: number, target: number): number {
  let value = seed ^ Math.imul(target, 0x45d9f3b);
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
  return ((value ^ (value >>> 16)) >>> 0) / 0x100000000;
}

function noiseTarget(seed: number, target: number): Point {
  const angle = seededUnit(seed, target) * Math.PI * 2;
  const radius = .2 + .8 * Math.sqrt(seededUnit(seed ^ 0x68bc21eb, target));
  return [Math.cos(angle) * radius, Math.sin(angle) * radius];
}

// Each point stays between the same two deterministic targets for several
// seconds. Cache those targets, not the interpolated frame, so arbitrary time
// jumps and independently seeded ribbons retain exactly the same trajectory.
const TARGET_CACHE_LIMIT = 64;
const targetCache = new Map<number, { target: number; from: Point; to: Point }>();
function targetPair(seed: number, target: number) {
  const previous = targetCache.get(seed);
  if (previous?.target === target) return previous;
  const pair = {
    target,
    from: previous?.target === target - 1 ? previous.to : noiseTarget(seed, target),
    to: noiseTarget(seed, target + 1),
  };
  if (!previous && targetCache.size >= TARGET_CACHE_LIMIT) {
    const oldest = targetCache.keys().next().value;
    if (oldest !== undefined) targetCache.delete(oldest);
  }
  targetCache.set(seed, pair);
  return pair;
}

/** Seeded two-dimensional value noise. Every target has its own direction and
 * distance; quintic interpolation keeps velocity and acceleration continuous
 * across target boundaries without wrapping a repeating animation timeline.
 */
export function flowNoise(seed: number, seconds: number, interval: number): Point {
  const time = seconds / interval, target = Math.floor(time), fraction = time - target;
  const blend = fraction ** 3 * (fraction * (fraction * 6 - 15) + 10);
  const { from, to } = targetPair(seed, target);
  return [from[0] + (to[0] - from[0]) * blend, from[1] + (to[1] - from[1]) * blend];
}

// Accelerate the entire existing trajectory equally, including its slow drift.
const FLOW_SPEED = 1.3;
const MOTION = [0, 1].map(index => BASE[index].map((_, point) => {
  const seed = (index + 1) * 1709 + point * 7919;
  const interval = [8, 8.9][index] * (.92 + .16 * seededUnit(seed, 0)) / FLOW_SPEED;
  const offset = seededUnit(seed ^ 0x9e3779b9, 0) * interval;
  const slowInterval = [29, 37][index] / FLOW_SPEED, slowSeed = seed ^ 0x27d4eb2d;
  const slowOffset = seededUnit(slowSeed, 0) * slowInterval;
  const start = flowNoise(seed, offset, interval), slowStart = flowNoise(slowSeed, slowOffset, slowInterval);
  const envelope = point === 0 || point === 5 ? 0 : Math.sin(Math.PI * point / 5) ** 2;
  return { seed, interval, offset, slowSeed, slowInterval, slowOffset, start, slowStart, envelope };
}));

function displacement(index: number, seconds: number, point: number): Point {
  // The same endpoints anchor every frame. The smooth spatial envelope makes
  // the centre supple while progressively quieting the ends of each thread.
  if (point === 0 || point === 5) return [0, 0];
  const motion = MOTION[index][point];
  const main = flowNoise(motion.seed, seconds + motion.offset, motion.interval);
  const slow = flowNoise(motion.slowSeed, seconds + motion.slowOffset, motion.slowInterval);
  const value = (axis: number) => .82 * (main[axis] - motion.start[axis]) + .18 * (slow[axis] - motion.slowStart[axis]);
  return [value(0) * 45 * motion.envelope, value(1) * 40 * motion.envelope];
}

/** Original composition at t=0. Each wave retains its own phases and C1 join.
 * A smooth p=8 norm includes the reflected S handle: every actual cubic control
 * stays within32/24 world px (about25/19 CSS px at1366x768). Convexity and the
 * certified baseline distance>70 imply centerline separation>14px for ALL times,
 * above the bright-core halfwidth sum12.5. No time wrapping or frame randomness.
 * The third curve is static diffuse ambient light, without a recognizable core.
 */
export function ribbonFrame(index: number, seconds: number): WaveFrame {
  if (index === 2 || seconds === 0) return { index, cubics: cubics(BASE[index]) };
  const raw = BASE[index].map((_, point) => displacement(index, seconds, point));
  const actual = [...raw, [2 * raw[3][0] - raw[2][0], 2 * raw[3][1] - raw[2][1]] as Point];
  const limit = CONTROL_DISPLACEMENT_LIMITS[index];
  const scale = limit / Math.pow(limit ** 8 + actual.reduce((sum, point) => sum + Math.hypot(...point) ** 8, 0), 1 / 8);
  return { index, cubics: cubics(BASE[index].map((point, i) => [point[0] + raw[i][0] * scale, point[1] + raw[i][1] * scale])) };
}
export function ribbonPath(frame: WaveFrame): string {
  const [first, second] = frame.cubics;
  const point = (value: Point) => `${value[0].toFixed(4)} ${value[1].toFixed(4)}`;
  return `M ${point(first[0])} C ${point(first[1])} ${point(first[2])} ${point(first[3])} S ${point(second[2])} ${point(second[3])}`;
}
export function cubicPoint(curve: Cubic, t: number): Point {
  const q = 1 - t;
  return [0, 1].map(axis => q ** 3 * curve[0][axis] + 3 * q * q * t * curve[1][axis] + 3 * q * t * t * curve[2][axis] + t ** 3 * curve[3][axis]) as unknown as Point;
}
export function flattenWave(frame: WaveFrame): readonly Point[] {
  return frame.cubics.flatMap(curve => Array.from({ length: 33 }, (_, i) => cubicPoint(curve, i / 32)));
}
