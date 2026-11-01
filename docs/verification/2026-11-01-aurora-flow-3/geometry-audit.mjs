import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { stripTypeScriptTypes } from 'node:module';

// Read-only production geometry audit. Exposing MOTION in memory lets this
// standalone artifact inspect the actual target boundaries without modifying
// application files or duplicating the production seed/interval calculation.
const sourceUrl = new URL('../../../frontend/src/features/auth/ribbonGeometry.ts', import.meta.url);
const source = readFileSync(sourceUrl, 'utf8');
const js = stripTypeScriptTypes(source + '\nexport { MOTION as auditMotion };');
const { ribbonFrame, cubicPoint, flowNoise, CONTROL_DISPLACEMENT_LIMITS, auditMotion } =
  await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const sample = frame => frame.cubics.flatMap(curve =>
  Array.from({ length: 33 }, (_, j) => cubicPoint(curve, j / 32)));
const seconds = 180, hz = 120, dt = 1 / hz;
const results = [];

for (const index of [0, 1]) {
  const initialFrame = ribbonFrame(index, 0), initial = sample(initialFrame);
  let previous = initial, velocity = initial.map(() => [0, 0]);
  let maxShift = 0, maxSpeed = 0, maxAcceleration = 0, maxControlShift = 0;
  let maxStep30 = 0, maxControlStep30 = 0, minXControlGap = Infinity;
  let anchorError = 0, c1Error = 0;
  for (let tick = 1; tick <= seconds * hz; tick++) {
    const time = tick * dt, frame = ribbonFrame(index, time), points = sample(frame);
    points.forEach((point, j) => {
      const nextVelocity = [(point[0] - previous[j][0]) / dt, (point[1] - previous[j][1]) / dt];
      maxShift = Math.max(maxShift, distance(point, initial[j]));
      maxSpeed = Math.max(maxSpeed, Math.hypot(...nextVelocity));
      if (tick > 1) maxAcceleration = Math.max(maxAcceleration, distance(nextVelocity, velocity[j]) / dt);
      velocity[j] = nextVelocity;
    });
    frame.cubics.flat().forEach((point, j) => {
      maxControlShift = Math.max(maxControlShift, distance(point, initialFrame.cubics.flat()[j]));
    });
    for (const curve of frame.cubics) for (let j = 1; j < 4; j++) {
      minXControlGap = Math.min(minXControlGap, curve[j][0] - curve[j - 1][0]);
    }
    anchorError = Math.max(anchorError,
      distance(frame.cubics[0][0], initialFrame.cubics[0][0]),
      distance(frame.cubics[1][3], initialFrame.cubics[1][3]));
    c1Error = Math.max(c1Error, distance(frame.cubics[1][1], [
      2 * frame.cubics[0][3][0] - frame.cubics[0][2][0],
      2 * frame.cubics[0][3][1] - frame.cubics[0][2][1],
    ]));
    if (tick % 4 === 0) {
      const old = ribbonFrame(index, time - 1 / 30), oldPoints = sample(old);
      points.forEach((point, j) => { maxStep30 = Math.max(maxStep30, distance(point, oldPoints[j])); });
      frame.cubics.flat().forEach((point, j) => {
        maxControlStep30 = Math.max(maxControlStep30, distance(point, old.cubics.flat()[j]));
      });
    }
    previous = points;
  }

  const motion = auditMotion[index].slice(1, 5);
  const targetDiversity = motion.map(({ seed, interval }) => {
    const targets = Array.from({ length: 24 }, (_, target) => flowNoise(seed, target * interval, interval));
    const radii = targets.map(point => Math.hypot(...point));
    return {
      seed, interval,
      quadrants: new Set(targets.map(([x, y]) => `${x > 0}:${y > 0}`)).size,
      minRadius: Math.min(...radii), maxRadius: Math.max(...radii),
      allAdjacentTargetsDifferent: targets.every((point, j) => !j || distance(point, targets[j - 1]) > 1e-6),
    };
  });

  // Inspect actual main and slow boundaries with one-sided finite differences.
  // The reported small differences are finite-resolution residuals, not jumps.
  const h = .001;
  let boundaryCount = 0, maxVelocityMismatch = 0, maxAccelerationMismatch = 0;
  for (const pointMotion of motion) {
    for (const [interval, offset] of [[pointMotion.interval, pointMotion.offset], [pointMotion.slowInterval, pointMotion.slowOffset]]) {
      for (let target = 1; target * interval - offset < seconds; target++) {
        const t = target * interval - offset;
        if (t <= 2 * h) continue;
        boundaryCount++;
        const frames = [-2, -1, 0, 1, 2].map(step => ribbonFrame(index, t + step * h).cubics.flat());
        for (let point = 0; point < frames[0].length; point++) {
          const velLeft = [0, 1].map(axis => (frames[2][point][axis] - frames[1][point][axis]) / h);
          const velRight = [0, 1].map(axis => (frames[3][point][axis] - frames[2][point][axis]) / h);
          const accLeft = [0, 1].map(axis => (frames[2][point][axis] - 2 * frames[1][point][axis] + frames[0][point][axis]) / h ** 2);
          const accRight = [0, 1].map(axis => (frames[4][point][axis] - 2 * frames[3][point][axis] + frames[2][point][axis]) / h ** 2);
          maxVelocityMismatch = Math.max(maxVelocityMismatch, distance(velLeft, velRight));
          maxAccelerationMismatch = Math.max(maxAccelerationMismatch, distance(accLeft, accRight));
        }
      }
    }
  }

  const centre = time => cubicPoint(ribbonFrame(index, time).cubics[0], .65);
  const route = Array.from({ length: 24 }, (_, segment) => centre(segment * 8));
  const increments = route.slice(1).map((point, j) => [point[0] - route[j][0], point[1] - route[j][1]]);
  const movementDepths = increments.map(point => Math.hypot(...point));
  results.push({
    index, maxCentrelineDisplacementWorld: maxShift,
    maxCentrelineDisplacementCssAt900High: maxShift * .9,
    maxCentrelineDisplacementCssAt768High: maxShift * .768,
    maxCentrelineSpeedWorldPerSecond: maxSpeed,
    maxCentrelineAccelerationWorldPerSecondSquared: maxAcceleration,
    maxCentrelineStepAt30HzWorld: maxStep30, maxControlStepAt30HzWorld: maxControlStep30,
    maxControlShiftWorld: maxControlShift, controlLimitWorld: CONTROL_DISPLACEMENT_LIMITS[index],
    minCubicXControlGapWorld: minXControlGap, anchorErrorWorld: anchorError, c1ErrorWorld: c1Error,
    targetDiversity, boundaryCount,
    maxBoundaryVelocityMismatchAt1msWorldPerSecond: maxVelocityMismatch,
    maxBoundaryAccelerationMismatchAt1msWorldPerSecondSquared: maxAccelerationMismatch,
    centreline8SecondIncrementQuadrants: new Set(increments.map(([x, y]) => `${x > 0}:${y > 0}`)).size,
    centreline8SecondIncrementDepthRangeWorld: [Math.min(...movementDepths), Math.max(...movementDepths)],
    checks: {
      controlsWithinCaps: maxControlShift <= CONTROL_DISPLACEMENT_LIMITS[index],
      anchoredEndpoints: anchorError === 0, c1JoinExact: c1Error === 0,
      monotonicXNoLoops: minXControlGap > 0,
      targetsVaryDirectionAndDepth: targetDiversity.every(item => item.quadrants === 4 && item.maxRadius - item.minRadius > .4 && item.allAdjacentTargetsDifferent),
    },
  });
}

const report = {
  generatedAtUtc: new Date().toISOString(),
  source: 'frontend/src/features/auth/ribbonGeometry.ts',
  sourceSha256: createHash('sha256').update(source).digest('hex'),
  method: 'Independent numeric audit of production geometry, source evaluated in memory with extra read-only MOTION export. No browser performance measurement.',
  seconds, hz, pointsPerCubic: 33,
  cssScalingAssumption: 'SceneMapping scale=.9 for980x900 and .768 for906x768/604x768. At1920x1080 scale=1460/1200, so multiply world values by1.2167.',
  results,
};
writeFileSync(new URL('./geometry-audit.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));

