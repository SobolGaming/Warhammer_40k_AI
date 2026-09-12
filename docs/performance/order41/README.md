# Order 41 component performance

This provisional component assessment measures active Shooting Stratagem option
enumeration on a real four-model scene, with no terrain, in three cases:
GRENADES, EXPLOSIVES, and an out-of-range target. Seven fresh scenes each measure
ten queries; setup is separate, with no discarded warm-up samples. No dice are
rolled in the measured query. Script, fixture, lock, runtime, CPU/memory and
engine-manifest identities, all samples and completion summaries are retained.

The same script and fixture run on main `5180254a` and head, using the same
interpreter and dependencies without competing test workers or coverage. The
incorrect base exposes no Explosives options in this timing window, so it is
only a cost comparison. Head must expose exactly two options in either keyword
case and none out of range.

The budget was fixed before the first head measurement: mean <= twice base plus
25 ms, with no sample-average query above 50 ms. An estimated 100 opportunity
queries would consume at most 5 seconds at that component threshold; that call
count is an estimate, not a measured full-game budget. No workload or threshold
is removed or raised after measurement. The required code-quality aggregate
checks retained comparability, completion, option counts and these bounds.

Reproduce with `PYTHONPATH=.:src uv run --no-sync python
scripts/measure_explosives_options.py --output docs/performance/order41/head.json`.
Export the base commit to an isolated directory and copy the identical script
and `tests/explosives_helpers.py` there. Use the same interpreter with that
checkout's `.:src` first on PYTHONPATH. The script reads macOS CPU/memory metadata.

Shared exact visibility caches retain their existing bounded-inventory and
invalidation tests; this change adds no cache. Gameplay-slice and complete-game
performance are not certified. The standing 60-second mean / 300-second observed
maximum game targets and Order 32 owner deferral remain unchanged.

On the provisional Apple M5 Pro / Python 3.14.5 host, all cases completed and
passed the unchanged budgets. Head means were 4.655 ms (GRENADES), 4.366 ms
(EXPLOSIVES), and 1.792 ms (out of range); the maximum sample-average query was
4.877 ms. Base queries were below 0.001 ms because the old catalog had no
matching during-phase option. This does not compare equivalent gameplay work.
