# Independent Visual QA — 2026-11-01

Result: PASS on the final seeded-noise implementation accelerated by 1.3× per the user's latest request. The nominal primary target intervals are approximately 6.15 seconds for the main ribbon and 6.85 seconds for the lower ribbon, with independently seeded variation and slower secondary motion.

Reviewed geometry source: `frontend/src/features/auth/ribbonGeometry.ts`, SHA256 `814CF9A96C543D9CF62C7A1EAA9B9E56B2013E494FACB91141B1CD40304D3ACA`.

Reviewed the actual running frontend at `http://127.0.0.1:5174/login` using installed Chrome in headless mode, with only unauthenticated API responses mocked. No frontend source files were changed by QA.

## Visual inspection

Opened and inspected screenshots at 0, 15, 31 and approximately 64 seconds, reduced motion, and all requested sizes: 1920×1080, 1440×900, 1366×768, 1024×768 and 390×844.

- The main diagonal and subdued lower arc retain their composition. Their interior curvature changes independently while endpoints remain fixed.
- The curves remain smooth. No observed loops, sharp corners, layer separation, or unreadable logo overlap in the inspected phases.
- Outer glow, coloured body and core remain aligned because all layers reference the same animated SVG paths.
- The original white brand mark remains stationary and readable. Desktop and mobile layout remain intact; every requested size has no horizontal overflow and the login button remains in the viewport.
- Mobile displays a static, subdued background and retains the small official brand mark above the form.
- No visible flash or geometry reset was found in the measured movement or pause/resume checks.

## Browser evidence

`browser-review.json` records the independently executed checks on the final 1.3× speed. The real-time sample lasted 31,002.1 ms with 4,453 measured frame intervals: p95 7.1 ms, maximum 27.8 ms, one interval above 25 ms, zero intervals above 50 ms and zero reported long tasks. This is review workload including screenshot and pixel-read operations, not a claim of universal frame rate or a substitute for the separate clean before/after renderer benchmark.

The two path control sets moved by up to 16.49 and 15.27 world pixels between the first and last captured real-time phases. Unequal per-control displacement proves deformation rather than translation. Start and end anchors were unchanged, movement differed between ribbons, and the static ambient source was unchanged.

Additional checks passed:

- Identical deterministic animation clocks with and without pointer movement produced identical path data and canvas pixel hashes.
- No Aurora mouse or pointer movement/leave listeners remained on `window` or `document`; React's delegated root listeners were allowed.
- Exactly one production animation frame was pending.
- Checkbox Space pauses and resumes. All light pixels freeze when paused or under live reduced motion. The animation checkbox is disabled while reduced motion is active.
- After a paused clock advanced 600 frames, resuming with a 30-second timestamp gap preserved the first resumed frame exactly; subsequent frames continued movement.
- Space was not intercepted inside email/password inputs, buttons or links. No global body Space shortcut existed beforehand; the existing checkbox keyboard control is preserved.
- Eight samples spaced eight seconds apart through 64 seconds produced eight distinct shapes for each ribbon; see `eight-second-targets.json`. Eight seconds is the sampling interval, independent of the final motion target duration.
- No browser page errors occurred.

`late-target.cjs` independently reproduced the final 64-second phase with no dialog; `controlled-high-motion-64s.png` is the inspected late-phase screenshot.

Final source login E2E: `npm.cmd run test:e2e -- e2e/login.spec.ts` passed all four tests in 14.2 seconds with exit code 0; see `e2e.log`. This includes login composition, original logo, particles, pause, reduced motion, site selection, keyboard access, errors, pending state, password visibility and return-route behavior. The Node warning about `NO_COLOR` and `FORCE_COLOR` is environmental and did not fail execution.

## Reproduction

From the worktree root, with the frontend already running:

```powershell
$env:FIXRATE_BASE_URL = 'http://127.0.0.1:5174'
node var/aurora-flow-3-qa/browser-review.cjs
node var/aurora-flow-3-qa/late-target.cjs
```

Limit: this review uses local Chrome and responsive emulation, not a physical office computer or mobile device. The before/after performance report and frontend typecheck/build/unit results are owned by the director and React Engineer.
