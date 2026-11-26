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
