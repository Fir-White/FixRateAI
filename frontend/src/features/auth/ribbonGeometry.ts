export type RibbonPointer = { x: number; y: number; strength: number };
type Point = readonly [number, number];

export const FLOW_WIDTH = 1200;
export const FLOW_HEIGHT = 1000;

const RIBBONS: { points: readonly Point[]; speed: number; phase: number }[] = [
  { points: [[-180, 1140], [90, 1030], [480, 760], [590, 470], [870, -20], [910, -260]], speed: 0.17, phase: 0.4 },
  { points: [[220, 1260], [360, 960], [710, 720], [1000, 625], [1380, 500], [1500, 320]], speed: 0.113, phase: 2.6 },
  { points: [[-280, 340], [60, 640], [460, 540], [720, 190], [1170, -80], [1510, 160]], speed: 0.079, phase: 4.9 },
];
const AMPLITUDES = [12, 62, 86, 58, 78, 14];

/** Two joined cubic Beziers. SVG S reflects the previous handle, preserving a smooth join. */
export function ribbonPath(index: number, seconds: number, pointer?: RibbonPointer): string {
  const ribbon = RIBBONS[index];
  const points = ribbon.points.map(([baseX, baseY], point) => {
    const phase = ribbon.phase + point * 0.83;
    const time = seconds * ribbon.speed;
    const amplitude = AMPLITUDES[point];
    let x = baseX + Math.sin(time + phase) * amplitude * 0.7 + Math.sin(time * 0.431 + phase * 1.7) * amplitude * 0.22;
    let y = baseY + Math.sin(time * 0.79 + phase * 1.2) * amplitude + Math.cos(time * 0.367 + phase) * amplitude * 0.27;

    if (pointer) {
      const dx = pointer.x - x;
      const dy = pointer.y - y;
      // A bounded local field bends nearby handles, leaving distant sections almost untouched.
      const influence = Math.exp(-(dx * dx + dy * dy) / (2 * 260 * 260)) * Math.max(0, Math.min(1, pointer.strength));
      x += Math.max(-1, Math.min(1, dx / 260)) * 32 * influence;
      y += Math.max(-1, Math.min(1, dy / 260)) * 32 * influence;
    }
    return `${x.toFixed(2)} ${y.toFixed(2)}`;
  });

  return `M ${points[0]} C ${points[1]} ${points[2]} ${points[3]} S ${points[4]} ${points[5]}`;
}
