import { describe, expect, it } from "vitest";
import { ribbonPath } from "./ribbonGeometry";

const coordinates = (path: string) => [...path.matchAll(/-?\d+(?:\.\d+)?/g)].map(match => Number(match[0]));

describe("light ribbon geometry", () => {
  it("has independent, continuous curves over long time spans", () => {
    expect(new Set([0, 1, 2].map(index => ribbonPath(index, 0))).size).toBe(3);
    for (const time of [0, 1, 40, 120, 600, 3600]) {
      for (const ribbon of [0, 1, 2]) {
        const current = coordinates(ribbonPath(ribbon, time));
        const next = coordinates(ribbonPath(ribbon, time + 1 / 144));
        expect(current).toHaveLength(12);
        current.forEach((value, index) => {
          expect(Number.isFinite(value)).toBe(true);
          expect(Math.abs(next[index] - value)).toBeLessThan(0.5);
        });
      }
    }
  });

  it("limits cursor influence to nearby sections instead of translating the entire curve", () => {
    const base = coordinates(ribbonPath(0, 10));
    const bent = coordinates(ribbonPath(0, 10, { x: base[4] + 100, y: base[5] - 100, strength: 1 }));
    const nearest = Math.hypot(bent[4] - base[4], bent[5] - base[5]);
    const distant = Math.hypot(bent[0] - base[0], bent[1] - base[1]);
    expect(nearest).toBeGreaterThan(5);
    expect(distant).toBeLessThan(nearest * 0.2);
    bent.forEach((value, index) => expect(Math.abs(value - base[index])).toBeLessThanOrEqual(32));
    expect(ribbonPath(0, 10, { x: 600, y: 500, strength: 0 })).toBe(ribbonPath(0, 10));
  });
});
