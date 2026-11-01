"""Independent all-time geometry certificate; no application imports or writes.

Run from the worktree: python -X utf8 docs/verification/2026-11-01-aurora-open-scene/geometry-certificate.py

This certifies the EXISTING composition for control budgets 48/36.
It does not sample time and is independent of the chosen seeded interpolant.
Assumptions: fixed outer endpoints, reflected S handle, unchanged global p=8
limiter.  The limiter's sum must include ALL distinct actual control offsets,
including reflected S handle.  The source hash and baseline inputs are reported.

The limiter implies sum_i ||d_i||^8 < L^8.  At Bezier parameter t, Holder gives
||sum_i B_i(t)*d_i|| <= L*(sum_i B_i(t)^(8/7))^(7/8), over moving controls only.
We bound each Bernstein weight on a parameter interval at its endpoints and
interior critical point, bound the baseline curve by a de Casteljau AABB, and
subtract both excursion envelopes from the baseline AABB distance.  Subdivide
until every pair is separated.  A positive floating-point guard is required.

For x-monotonicity, generic adjacent varying controls differ by at most
L*2^(7/8).  At the shared C1 handle/junction the three offsets are a,b,2b-a.
For fixed d=b-a, |a|^8+|b|^8+|2b-a|^8 is minimized at b=0 and equals 2|d|^8.
Thus that adjacent difference is bounded by L/2^(1/8).  Fixed-end differences
are bounded by L.  Positive control x-gaps imply derivative x>0, ruling out
loops, cusps and reversal regardless of time.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re

Point = tuple[float, float]
Curve = tuple[Point, Point, Point, Point]
FLOAT_GUARD = 1e-7


def baseline_from_source(source: str) -> tuple[list[list[Curve]], dict]:
    def array(name: str, multiline: bool = False):
        expression = rf"\b{name}\s*=\s*(\[[\s\S]*?\n\])" if multiline else rf"\b{name}\s*=\s*(\[[^\]]*\])"
        match = re.search(expression, source)
        if match is None:
            raise ValueError(f"Cannot find original composition array {name}")
        return ast.literal_eval(match.group(1))

    sources = array("SOURCES", True)
    phases, amplitudes = array("PHASES"), array("AMPLITUDES")
    # These are the unchanged originalPoints equations in ribbonGeometry.ts.
    # Python and JS binary doubles agree here after the source's 2-digit round;
    # explicit baseline controls are included in the result for independent use.
    curves = []
    for index in (0, 1):
        points = []
        for number, (x, y) in enumerate(sources[index]):
            phase = phases[index] + number * .83
            amplitude = amplitudes[number]
            points.append((
                round(x + math.sin(phase) * amplitude * .7 + math.sin(phase * 1.7) * amplitude * .22, 2),
                round(y + math.sin(phase * 1.2) * amplitude + math.cos(phase) * amplitude * .27, 2),
            ))
        reflected = (2 * points[3][0] - points[2][0], 2 * points[3][1] - points[2][1])
        curves.append([tuple(points[:4]), (points[3], reflected, points[4], points[5])])
    return curves, {"SOURCES": sources, "PHASES": phases, "AMPLITUDES": amplitudes}


def mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def split(curve: Curve) -> tuple[Curve, Curve]:
    a, b, d = mid(curve[0], curve[1]), mid(curve[1], curve[2]), mid(curve[2], curve[3])
    e, f = mid(a, b), mid(b, d)
    g = mid(e, f)
    return (curve[0], a, e, g), (g, f, d, curve[3])


def box(curve: Curve) -> tuple[float, float, float, float]:
    return min(p[0] for p in curve), min(p[1] for p in curve), max(p[0] for p in curve), max(p[1] for p in curve)


def bernstein(index: int, t: float) -> float:
    return ((1-t)**3, 3*t*(1-t)**2, 3*t*t*(1-t), t**3)[index]


def envelope(segment: int, low: float, high: float) -> float:
    moving = (1, 2, 3) if segment == 0 else (0, 1, 2)
    def weight_upper(index: int) -> float:
        values = [bernstein(index, low), bernstein(index, high)]
        critical = {1: 1/3, 2: 2/3}.get(index)
        if critical is not None and low <= critical <= high:
            values.append(bernstein(index, critical))
        return max(values)
    return sum(weight_upper(i)**(8/7) for i in moving)**(7/8)


def certificate(curves: list[list[Curve]], limits: tuple[float, float], clearance: float, max_depth: int) -> dict:
    calls, deepest, leaves, min_leaf = 0, 0, 0, math.inf
    def certify(a: Curve, ai: int, al: float, ah: float,
                b: Curve, bi: int, bl: float, bh: float, depth: int = 0) -> bool:
        nonlocal calls, deepest, leaves, min_leaf
        calls += 1
        deepest = max(deepest, depth)
        x, y = box(a), box(b)
        dx, dy = max(0, x[0]-y[2], y[0]-x[2]), max(0, x[1]-y[3], y[1]-x[3])
        lower = math.hypot(dx, dy) - limits[0]*envelope(ai, al, ah) - limits[1]*envelope(bi, bl, bh)
        if lower > clearance + FLOAT_GUARD:
            leaves += 1
            min_leaf = min(min_leaf, lower)
            return True
        if depth >= max_depth:
            return False
        if math.hypot(x[2]-x[0], x[3]-x[1]) >= math.hypot(y[2]-y[0], y[3]-y[1]):
            left, right = split(a)
            m = (al+ah)/2
            return certify(left, ai, al, m, b, bi, bl, bh, depth+1) and certify(right, ai, m, ah, b, bi, bl, bh, depth+1)
        left, right = split(b)
        m = (bl+bh)/2
        return certify(a, ai, al, ah, left, bi, bl, m, depth+1) and certify(a, ai, al, ah, right, bi, m, bh, depth+1)

    pairs = [{"segments": [ai, bi], "passed": certify(a, ai, 0, 1, b, bi, 0, 1)}
             for ai, a in enumerate(curves[0]) for bi, b in enumerate(curves[1])]
    return {"method": "de Casteljau AABB + interval Bernstein/Holder p=8 bound",
            "all_time_centerline_clearance_gt": clearance,
            "bright_core_halfwidth_sum": 9/2 + 16/2,
            "floating_point_guard": FLOAT_GUARD,
            "pairs": pairs, "calls": calls, "max_depth_used": deepest,
            "certified_leaf_pairs": leaves, "minimum_leaf_lower_bound": min_leaf,
            "passed": all(pair["passed"] for pair in pairs)}


def x_gap_certificate(curves: list[list[Curve]], limits: tuple[float, float]) -> dict:
    result = []
    for index, (wave, limit) in enumerate(zip(curves, limits)):
        segments = []
        for segment, curve in enumerate(wave):
            gaps = []
            for point in (1, 2, 3):
                baseline_gap = curve[point][0] - curve[point-1][0]
                if (segment == 0 and point == 1) or (segment == 1 and point == 3):
                    variation, kind = limit, "one fixed global endpoint"
                elif (segment == 0 and point == 3) or (segment == 1 and point == 1):
                    variation, kind = limit/2**(1/8), "coupled reflected C1 handle"
                else:
                    variation, kind = limit*2**(7/8), "two varying controls"
                gaps.append({"baseline_gap": baseline_gap, "offset_difference_bound": variation,
                             "all_time_gap_lower_bound": baseline_gap-variation, "bound": kind})
            segments.append(gaps)
        minimum = min(gap["all_time_gap_lower_bound"] for segment in segments for gap in segment)
        result.append({"ribbon": index, "segments": segments, "minimum_guaranteed_gap": minimum,
                       "passed": minimum > FLOAT_GUARD})
    return {"method": "p8 energy bounds on actual adjacent controls, including reflected S handle",
            "ribbons": result, "passed": all(wave["passed"] for wave in result)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[3]/"frontend/src/features/auth/ribbonGeometry.ts")
    parser.add_argument("--first", type=float, default=48)
    parser.add_argument("--second", type=float, default=36)
    parser.add_argument("--clearance", type=float, default=15)
    parser.add_argument("--max-depth", type=int, default=32)
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    curves, inputs = baseline_from_source(source)
    limits = (args.first, args.second)
    separation = certificate(curves, limits, args.clearance, args.max_depth)
    orientation = x_gap_certificate(curves, limits)
    result = {"scope": "Independent read-only mathematical geometry review; no temporal sampling, browser/performance or application tests",
              "source": str(args.source.resolve()), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "source_control_budget_declaration": re.search(r"CONTROL_DISPLACEMENT_LIMITS\s*=\s*(\[[^\]]*\])", source).group(1),
              "proposed_control_budgets": limits, "baseline_inputs": inputs, "baseline_cubics": curves,
              "assumptions": ["originalPoints equations unchanged", "fixed outer endpoints", "reflected S handle", "global p8 limiter includes all actual controls including reflected handle"],
              "separation": separation, "orientation_and_no_loops": orientation,
              "passed": separation["passed"] and orientation["passed"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
