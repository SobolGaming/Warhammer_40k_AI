# Order 84 validation and performance evidence

Order 87 refreshed the active head report for runtime `904893c1`; prior tables and
revision notes below describe historical runs. Current samples and refresh details
are recorded in [Order 87 evidence](../order87/README.md). Baselines and budgets
remain unchanged.

`review.json` records the independent review/fix loop and final runtime approval
before the first push. `validation.json` records final commands and results,
including the initial unsuccessful aggregate attempt and its corrections.

## Matched dice component workload

`base.json` and `head.json` run the same versioned
`scripts/measure_order84.py` workload, lock file, interpreter and provisional
hardware. The base is an exported `src/` tree from
`c79e1c816cfc1bf0fca6676e6ecbf7c4bab407a0`; the head is identified by its runtime
build hash. The final matched pair was measured after implementation, using the
unchanged base export. It is not a preimplementation measurement.

Each case runs seven samples of 1,000 state constructions, optional assignment,
payload restoration, physical-component interpretation and modifier construction.
Cases use physical 1D6, physical 2D6 and a source-assigned six on 1D6, which both
versions can represent. Assigned seven and multi-component assignment correctness
are covered behaviorally; the unsupported base cannot serve as their correctness
oracle. The benchmark makes no random draws or geometry queries.

The versioned budget permits a mean of at most `base * 1.75 + 0.05` seconds and a
maximum of one second per 1,000 iterations. This is a diagnostic component ceiling,
not an allocation against a complete game's time target. The budget was not raised
to accommodate final measurements. The code-quality gate checks matched inputs,
current runtime and script hashes, sample completeness and these limits.

Reproduce on an idle host, without coverage:

```sh
PYTHONPATH=.:src uv run --no-sync python scripts/measure_order84.py \
  --runtime-src /path/to/base/src \
  --revision c79e1c816cfc1bf0fca6676e6ecbf7c4bab407a0 \
  --output docs/performance/order84/base.json
PYTHONPATH=.:src uv run --no-sync python scripts/measure_order84.py \
  --runtime-src src --revision '<current runtime build ID>' \
  --output docs/performance/order84/head.json
```

## Inherited evidence and limits

`inherited-refresh.json` records the existing benchmark commands, output hashes
and completion times. Runtime-pinned head reports are refreshed serially without
competing test/build workers; inherited baselines and budgets remain unchanged.
These component and gameplay-slice measurements do not certify full games.
Order 32's deferred component gates remain deferred, and the standing full-game
mean below 60 seconds / observed maximum below 300 seconds remains unverified.
