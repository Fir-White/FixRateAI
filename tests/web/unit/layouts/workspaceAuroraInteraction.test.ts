import { describe, expect, it } from "vitest";
import { createWorkspaceAuroraInteraction } from "@/layouts/workspaceAuroraInteraction";

function scene(width = 1200, height = 900) {
  const spring = createWorkspaceAuroraInteraction();
  spring.resize(width, height);
  spring.ribbons.forEach((points, wave) => points.forEach((point, index) => {
    point.x = index * 25; point.y = wave ? 750 : 300;
  }));
  return spring;
}

describe("local workspace response", () => {
  it.each([.15, .5, .85])("repels the clicked section at %s without moving distant sections or endpoints", position => {
    const spring = scene();
    spring.nudge(position, 290 / 900, 1);
    expect(spring.ribbons[0].every(point => point.dx === 0 && point.dy === 0)).toBe(true);
    spring.step(.05);
    const ribbon = spring.ribbons[0];
    const peak = ribbon.reduce((best, point, index) => point.dy > ribbon[best].dy ? index : best, 0);
    expect(Math.abs(peak / 48 - position)).toBeLessThan(.025);
    expect(ribbon[peak].dy).toBeGreaterThan(1);
    const distant = ribbon[position < .5 ? 42 : 6];
    expect(Math.hypot(distant.dx, distant.dy)).toBeLessThan(.03);
    expect(ribbon[0].dy).toBe(0); expect(ribbon[48].dy).toBe(0);
    expect(spring.ribbons[1].every(point => point.dx === 0 && point.dy === 0)).toBe(true);
    for (let frame = 0; frame < 160; frame++) spring.step(.05);
    expect(ribbon.every(point => Math.hypot(point.dx, point.dy) < .01)).toBe(true);
  });

  it("pushes away from either side and uses the displayed curve rather than fixed anchors", () => {
    const above = scene(); const below = scene();
    above.nudge(.5, 290 / 900, 1); below.nudge(.5, 310 / 900, 1);
    above.step(.05); below.step(.05);
    expect(above.ribbons[0][24].dy).toBeGreaterThan(0);
    expect(below.ribbons[0][24].dy).toBeLessThan(0);
    const moved = scene();
    moved.ribbons[0].forEach(point => { point.y = 50; point.dy = 250; });
    moved.nudge(.5, 290 / 900, 1); moved.step(.05);
    expect(moved.ribbons[0][24].dy).toBeGreaterThan(0);
  });

  it("bounds rapid input in CSS pixels, including a narrow viewport, and limits delayed frames", () => {
    const spring = scene(390, 844);
    for (let frame = 0; frame < 200; frame++) {
      spring.nudge(.5, 290 / 900, 1); spring.step(.05);
      expect(spring.ribbons.flat().every(point => Math.hypot(point.dx * 390 / 1200, point.dy * 844 / 900) <= 36.00001)).toBe(true);
    }
    const normal = scene(); const delayed = scene();
    normal.nudge(.5, 290 / 900, 1); delayed.nudge(.5, 290 / 900, 1);
    normal.step(.064); delayed.step(100);
    expect(delayed.ribbons).toEqual(normal.ribbons);
  });
});
