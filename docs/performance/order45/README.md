# Order 45: phase-end Fire Overwatch cost

The matched workload covers phase-end scheduling, friendly shooter selection,
one enemy declaration, ordinary attack resolution and continuation to the next
Shooting decision. Setup is measured separately. It uses three real models,
no terrain, one CP, a 24-inch weapon, two configured attacks and the same chosen
moved enemy on both revisions. The engine seeds dice from `order45-overwatch`
and its canonical event history. The decision policy accepts the shooter and
first enemy, declines optional Stratagems and selects the first remaining finite
option. No coverage, profiler or competing test workers ran during measurement.

The provisional host is Apple M5 Pro / macOS 26.6.2 / Python 3.14.5; CPU allocation,
memory, dependency lock and matching fixture/script hashes are in the JSON files.
Base is `a178a9e1ff5cac93c0c79e61499b2ce45f402012`. Head's runtime diff hash includes
the generated runtime manifest. Seven samples completed on each revision.

| Slice time | Base | Head |
| --- | ---: | ---: |
| Mean | 0.09400 s | 0.04086 s |
| Median | 0.09319 s | 0.03984 s |
| P95 / observed maximum | 0.09917 s | 0.04777 s |
| Decisions / events | 4 / 60 | 4 / 52 |

Changed request identity changes the seeded event history and dice path; these
numbers compare the cost of the same gameplay task, not identical attack rolls
or an isolated solver speedup. The old implementation is not a correctness oracle.
The final fixture records the opponent's authentic turn-start evidence before
shooting, including the evidence needed if a target is destroyed.

`budgets.json` was fixed before the head measurement: mean at most twice base
plus 25 ms, maximum 150 ms, at most four decisions and 55 events for this head
scenario. The additive margin accounts for scheduling noise in a short slice.
The measured head passes. One Overwatch window per eligible opponent per phase
replaces per-movement enumeration; the behavior and static gates enforce this
work bound. At ten phase-end opportunities in a five-round game, multiplying the
observed head mean gives approximately 0.41 seconds, an estimate for this tiny
scene only. Neither this slice nor its budget certifies component worst cases,
a complete gameplay workload or the standing 60/300-second full-game targets.

Reproduce from the repository root (on macOS, without competing workers):

```bash
PYTHONPATH=. uv run python scripts/measure_fire_overwatch.py --output /tmp/overwatch-head.json
```

For the base, create a detached checkout of the recorded base commit, copy the
same `tests/fire_overwatch_helpers.py` and `scripts/measure_fire_overwatch.py`,
and run with that checkout's `src` and root first on `PYTHONPATH`, using the same
locked Python environment. The benchmark's Git working directory must be that
checkout. Do not replace the committed reference results with another workload.
The fast required code-quality gate is `test_order45_fire_overwatch.py`.

The additional `ruin_scenarios.json` runs the unchanged Cavalcade exact-ruin
traversal and phase-end reserve-arrival tests on both checkouts, serially without
coverage on the same host/interpreter. Each case has one timing observation:
5.447 / 5.873 seconds for the ruin (base/head), and 0.963 / 1.038 for reserve arrival.
They pass the separate two-times-base-plus-0.5-second and 15-second limits fixed
before the head observation. These observations are diagnostic, not robust
percentile or worst-case evidence. Test-file and JUnit hashes are retained.

`eager_discovery_diagnostic.json` preserves the superseded prototype's 793.527-second
interrupted exact-visibility computation. The fix restores the ordinary optional
proposal boundary: a player may decline without computing every potential shot.
Choosing a shooter still requires current exact visibility and range validation
before CP spend. No solver, timeout semantics or battlefield geometry was changed.

The paired `rapid-ingress-base.json` and `rapid-ingress-head.json` preserve seven
samples of every existing Order 35 case. The same script and fixtures run
sequentially on both revisions. The decision policy now declines any newly valid
post-arrival Overwatch opportunity before requiring parent continuation. All
existing Order 35 mean, maximum and live work-count budgets remain unchanged and
pass. In particular, the complete placement mean is 0.16059 / 0.17903 seconds
(base/head); the additional optional choice is included. Discovery reuses the
current enumerated rules-unit view and does not resolve off-board reserve IDs
again. Historical Order 35 results remain untouched.

## R45-001 attached-unit check

The paired `r45-001-base.json` / `r45-001-head.json` compare reviewed commit
`6a2799b287076a55c9922e9d60f53d2a8032934c` with the range fix. Both runs use the
same script, fixtures, interpreter and hardware, serially without instrumentation
or concurrent workers. The stationary scenario has five models, attached
shooter and target groups, one CP, no terrain, two attacks, and one complete
Overwatch declaration/attack/continuation. Seven samples completed on each.

Mean: 0.04400 / 0.04268 seconds; observed maximum: 0.05819 / 0.04914 seconds
(base/head). Every sample has four decisions and 49 events. The existing
`budgets.json` timing and work-count limits apply unchanged and pass. The
correctness regressions separately cover the attached 24-inch boundary that
failed on the base; this timing case is legal on both revisions.

Reproduce with `PYTHONPATH=. uv run python scripts/measure_fire_overwatch.py
--attached --output /tmp/r45-001-head.json` (one shell line). Full-game performance
remains uncertified. Earlier evidence above is retained for its recorded builds.
