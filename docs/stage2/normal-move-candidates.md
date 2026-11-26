# Opt-in ordinary Normal Move candidates

Use the existing finite candidates to compare issued Remain Stationary with
Normal Move. After selecting Normal Move, call
`generate_normal_move_proposals` on the new actor-scoped proposal request. It
uses the same bounded, rigid, planar translation search as Fall Back, retaining
the complete placed model group and facing. It emits at most 32 full straight-line
witnesses for at most five movers and 256 visible models, or raises a typed gap.
The existing Fall Back options and path order are unchanged.

These are unranked alternatives, not certified legal paths or recommendations.
The native Normal Move submission still checks effective budget, traversal,
engagement range, and coherency. The generator reads no opponent policy,
objectives, outcomes, or hidden state and does not submit, score, or emit training
data. No flight-mode selection or alternate path planner is part of this search.

## Constructed native comparison

The [retained replay receipt](normal-move-candidate-receipt.json) uses the
locked round-four/round-five construction and one generated translation per
tested move. The test-only witness selectors are fixed geometric checks at
three quarters of the visible Move value. No score, checkpoint identity or
fixture geometry is an input to runtime candidate selection.

| Round-four S | Round-five S | Round-five E | Player A score |
| --- | --- | --- | ---: |
| Hold | Hold | Hold | 0 |
| Hold | Hold | Generated objective move | 0 |
| Generated screen | Hold | Hold | 0 |
| Generated screen | Hold | Generated objective move | 4 |
| Hold | Same generated screen | Generated objective move | 0 |

The same opposing reinforcement attempt lands without the early screen and
fails native engagement-range transit validation after it. Early and late S
use identical full witnesses; all three moving E arms use the same full
witness. S never supplies objective control. The common prefix and five final
histories reproduce their native event logs exactly and preserve checkpoint,
both viewer projections, and their event streams through JSON save/load.
Wounds, survival and RNG consumption remain unchanged. This is a constructed
local control, not historic reachability, a policy ranking, or a training label.

## Exact-base component control

The [serial component record](normal-move-exact-base-performance.json) takes
five 20-call samples on the same Windows host and dependency lock. Both Fall
Back modes retain byte-identical ordered actions. The finite actions, native
Normal Move request, and resulting actor observation and event log for an
ordinary submission also match exactly. Only the opt-in call performs the
translation search; it produced 32 candidates at a median of 8.42 ms per call
on this one open fixture. This is not a full-game or general latency claim.

To repeat the component probe, use the same copy of
[the measurement driver](../../tools/performance_stage2_normal_move.py) from
both repository roots, with their own Python source on the import path:

```sh
# Exact detached base checkout:
PYTHONPATH=src:. python -B /path/to/performance_stage2_normal_move.py base /tmp/normal-base.json
# Candidate checkout, same host and dependency lock:
PYTHONPATH=src:. python -B /path/to/performance_stage2_normal_move.py head /tmp/normal-head.json
```

The original component samples remain bound to c0235fe0. The later B3
evidence-only landing (#750) changed the draft base to e5cfe3ca, but left the
measured runtime, fixture, dependency lock and behavioral selection identical.
The [base successor record](normal-move-base-successor.json) records those
immutable Git objects. The serial performance gate binds the exact new draft
base and diff separately; the original samples are not relabeled or replaced.

## Frozen S and E decision-point timings

The [frontier receipt](normal-move-frontier-evidence.json) records three serial
samples per decision point on the same Windows runtime. Each sample restores
the same pending proposal, generates candidates once and submits only the
unique match. The predeclared predicate is a pure −Y move for S or +Y move
for E, at three quarters of the shortest visible Move. It is not exact
authored-path equality: the generated moves are 4.5-inch straight translations,
whereas the authored endpoints were 4.0 inches for S and 4.2 inches for E
with an intermediate waypoint. Every matched generated witness is identical to
the one used at that decision point in the retained scoring run.

Wall times below are in milliseconds, as median [minimum–maximum]:

| Decision point | Predicate matches | Exact authored XY-waypoint matches | Generate | Native resolution | Whole native submission |
| --- | ---: | ---: | ---: | ---: | ---: |
| S early A4 | 1/32 | 0 | 8.17 [7.95–8.20] | 13.38 [12.82–18.08] | 59.08 [57.89–65.59] |
| S late A5 | 1/32 | 0 | 8.53 [8.29–11.36] | 15.30 [14.61–15.83] | 148.00 [131.80–211.45] |
| E A5 after S held | 1/32 | 0 | 8.09 [8.08–8.46] | 13.24 [12.81–16.83] | 172.59 [166.18–177.82] |
| E A5 after early S | 1/32 | 0 | 7.94 [7.83–8.49] | 13.61 [13.38–13.63] | 171.34 [164.15–181.70] |
| E A5 after late S | 1/32 | 0 | 8.21 [8.03–8.57] | 13.26 [13.03–13.75] | 258.80 [255.89–259.30] |

Generation times the search on an already-built actor context. Native
resolution times the engine's grouped Normal Move path/rule resolver inside
the ordinary submission. The whole submission also includes actor binding,
application, events and the next request; it already includes the resolver time.
Restore, projection construction, predicate matching and result checks are
outside the timers. All 15 submissions were accepted and reproduced the
archived event and next-request identities. No other candidates were validated,
no opponent response was added, and no sample continued to scoring.

The [probe driver](../../tools/performance_stage2_normal_move_frontiers.py)
takes the retained generated checkpoint/ledger directory, authored reference
directory, immutable scoring receipt path, and an output path.
