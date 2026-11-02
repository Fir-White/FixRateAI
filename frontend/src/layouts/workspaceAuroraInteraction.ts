interface RibbonPoint { x: number; y: number; dx: number; dy: number }

/** Local normal impulses along the currently rendered ribbons, in CSS pixels. */
export function createWorkspaceAuroraInteraction(count = 49) {
  const ribbons = Array.from({ length: 2 }, () => Array.from({ length: count }, (): RibbonPoint => ({ x: 0, y: 0, dx: 0, dy: 0 })));
  const springs = ribbons.map(() => Array.from({ length: count }, (_, index) => ({
    x: 0, y: 0, vx: 0, vy: 0,
    edge: Math.sin(Math.min(1, index / 4, (count - 1 - index) / 4) * Math.PI / 2) ** 2,
  })));
  const lengths = new Float64Array(count);
  let scaleX = 1;
  let scaleY = 1;
  let width = 1200;
  let height = 900;

  return {
    ribbons,
    resize(nextWidth: number, nextHeight: number) {
      width = Math.max(1, nextWidth); height = Math.max(1, nextHeight);
      scaleX = width / 1200; scaleY = height / 900;
    },
    nudge(x: number, y: number, strength: number) {
      const clickX = x * width;
      const clickY = y * height;
      ribbons.forEach((points, wave) => {
        let nearest = Infinity;
        let hitLength = 0;
        let normalX = 0;
        let normalY = 0;
        lengths[0] = 0;
        for (let index = 0; index < count - 1; index++) {
          const first = points[index];
          const second = points[index + 1];
          const ax = (first.x + first.dx) * scaleX;
          const ay = (first.y + first.dy) * scaleY;
          const tx = (second.x + second.dx) * scaleX - ax;
          const ty = (second.y + second.dy) * scaleY - ay;
          const squared = tx * tx + ty * ty;
          const length = Math.sqrt(squared);
          lengths[index + 1] = lengths[index] + length;
          if (!length) continue;
          const t = Math.max(0, Math.min(1, ((clickX - ax) * tx + (clickY - ay) * ty) / squared));
          const rx = ax + t * tx - clickX;
          const ry = ay + t * ty - clickY;
          const distance = rx * rx + ry * ry;
          if (distance >= nearest) continue;
          nearest = distance;
          hitLength = lengths[index] + t * length;
          const nx = -ty / length;
          const ny = tx / length;
          const side = rx * nx + ry * ny;
          const direction = Math.abs(side) > .5 ? Math.sign(side) : wave ? -1 : 1;
          normalX = nx * direction;
          normalY = ny * direction;
        }
        if (nearest > 180 ** 2) return;
        const proximity = Math.exp(-nearest / (2 * 90 ** 2));
        const spread = Math.min(125, Math.max(75, width * .22));
        for (let index = 1; index < count - 1; index++) {
          const spring = springs[wave][index];
          const distance = lengths[index] - hitLength;
          const impulse = 185 * strength * proximity * Math.exp(-(distance ** 2) / (2 * spread ** 2)) * spring.edge;
          spring.vx += normalX * impulse;
          spring.vy += normalY * impulse;
          const limit = Math.min(1, 200 / (Math.hypot(spring.vx, spring.vy) || 1));
          spring.vx *= limit; spring.vy *= limit;
        }
      });
    },
    step(delta: number) {
      const duration = Math.min(.064, Math.max(0, delta));
      const steps = Math.max(1, Math.ceil(duration / .016));
      const dt = duration / steps;
      springs.forEach((nodes, wave) => nodes.forEach((spring, index) => {
        if (Math.abs(spring.x) + Math.abs(spring.y) + Math.abs(spring.vx) + Math.abs(spring.vy) < .0001) {
          spring.x = spring.y = spring.vx = spring.vy = 0;
          ribbons[wave][index].dx = ribbons[wave][index].dy = 0;
          return;
        }
        for (let substep = 0; substep < steps; substep++) {
          spring.vx += (-7.5 * spring.x - 3.5 * spring.vx) * dt;
          spring.vy += (-7.5 * spring.y - 3.5 * spring.vy) * dt;
          spring.x += spring.vx * dt; spring.y += spring.vy * dt;
        }
        const length = Math.hypot(spring.x, spring.y);
        const envelope = length ? 36 * Math.tanh(length / 36) / length : 1;
        ribbons[wave][index].dx = spring.x * envelope / scaleX;
        ribbons[wave][index].dy = spring.y * envelope / scaleY;
      }));
    },
  };
}
