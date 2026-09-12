# Order 42 Shooting revalidation performance

This provisional component/small-slice workload resumes a real accepted Shooting
selection through `LocalGameSession` to the next engine decision. It measures
15 models, two committed physical weapons and two enemy units without terrain,
using the existing deterministic `phase13b-game` seed and the first engine
resolution option. Cases retain eligible targets, a target moved out of range,
and no remaining legal target. Setup is measured separately. Seven fresh scenes
per case retain every sample; there is no discarded warm-up, coverage, profiling
or concurrent test worker in the timing run.

The base is `b3186efa6de212f98f146d0e2099ebffbf622fa5`, exported into an isolated
checkout. Both sides use exactly the same script, canonical fixture, uv lock,
interpreter and host. The incorrect base continues old targeting; it is a cost
comparison, not a correctness oracle. Head must expose a replacement with an
alternative plus decline, or only decline when no target is legal. The eligible
case must preserve the existing resolution path.

`budgets.json` was fixed before either retained measurement: head mean <= twice
base plus 50 ms, maximum <= 150 ms. An estimated 100 such boundaries costs at
most 5 seconds of additive mean overhead; that call count is an estimate against
the 60-second game objective, not a measured complete-game workload. The wider
maximum permits host variability while the comparative mean bounds ordinary
cost. No thresholds or cases are removed after measuring. Required code-quality
tests check comparability, complete sample counts, expected decisions and budgets;
the behavioral regressions check deterministic decisions and no extra dice/use.

Reproduce with `PYTHONPATH=.:src uv run --no-sync python
scripts/measure_target_replacement.py --output docs/performance/order42/head.json`.
For base, export the commit and copy the identical measurement script and
`tests/target_replacement_helpers.py` into it, then use the same interpreter with
that checkout's `.:src` first on PYTHONPATH. CPU/memory inspection needs normal
macOS process permissions. The first sandboxed attempt finished the workload but
could not read CPU metadata and produced no report; the retained base rerun
collected complete metadata. Hardware is provisional.

The declaration validator retains at most one pure model-target query. Its key
serializes every query input, including the complete scenario, rules descriptor,
weapon and unit profiles, terrain, hidden models, recent target shooting and
detection range. Nested RuleIR mappings are serialized rather than assumed
hashable. Runtime target restrictions are still evaluated after the query.
The cache is never persisted; cold/warm and range/hidden/placement invalidation,
casualty, retained-presence cleanup, restoration and independent-game regressions
preserve the same rules answers and typed absence errors. An eligibility-only revalidation
does not recalculate attack modifiers for an unchanged target. Existing Order 33
and Order 34 work budgets remain unchanged.

Component/small-slice evidence does not certify
complete head-to-head games, universal worst-case performance or the deferred
Order 32 budgets. Full-game 60-second mean / 300-second observed maximum targets
remain outstanding under the versioned performance policy.


The revised Apple M5 Pro / Python 3.14.5 head run after R42-001/002 passes
the fixed bounds. Runtime identity is
`5aa34244db47285239dc384b5b8addaeefdfc3705efa77350f0242ce6f25e647`.
The same committed workload and base evidence remain unchanged.
Eligible-target resolution averages 33.611 ms versus 17.717 ms on base. A moved
target averages 5.509 ms and no alternative averages 4.686 ms, because head stops
at the replacement decision while the incorrect base proceeds into attacks.
The maximum retained head sample is 68.148 ms. These latter cases measure
different rules work and do not establish an attack-resolution speedup.

## Out-of-phase reaction continuation

`measure_out_of_phase_target_replacement.py` measures the R42-002 follow-up:
four real models, no terrain, Unending Fidelity retained Shooting in Fight,
original defense declined, and a fresh replacement accepted. The timed boundary
is replacement submission to the next decision; all preparation is separate.
Seven fresh scenes retain every sample with no warm-up discarded. The fixed
`out_of_phase_budgets.json` uses the same 2x base plus 50 ms mean and 150 ms
maximum limits and rationale as the original Order 42 workload.

Base `72b4f781` incorrectly proceeds to target resolution. Head must stop at the
fresh target's Unending Fidelity window. This is a cost comparison between
different rules work, not an attack-resolution speedup. It measures the reaction
window, not the separately documented RuleIR effect-identity collision when
both players accept the same Stratagem in a phase.

Reproduce head with `PYTHONPATH=.:src uv run --no-sync python
scripts/measure_out_of_phase_target_replacement.py --output
docs/performance/order42/out_of_phase_head.json`. Export `72b4f781` to a separate
directory, copy the identical measurement script and
`tests/target_replacement_reaction_helpers.py`, and run the same interpreter with
that checkout's `.:src` first on `PYTHONPATH` to reproduce base. Retained reports
include script/fixture/runtime hashes, provisional host and dependency identity,
all samples, summary statistics, throughput and completion rate. The static
quality gate checks comparable inputs, exact expected decisions and fixed costs.

The retained follow-up reports pass these bounds: base averages 35.779 ms and
head averages 24.675 ms, with a 24.927 ms maximum on head. Every head sample
offers exactly the fresh target's Unending Fidelity option and decline. The head
runtime fingerprint is
`a9fddc3459c8f12b859c9c37c3c13e71cbf822a7c65b57ed9f00cb33bbff9d75`.
