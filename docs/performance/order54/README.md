# Order 54 performance and delivery evidence

## Initial implementation evidence

The matched uninstrumented component workload resolves four deployments with
identical real canonical armies, 200 mm base, battlefield and proposal inputs.
The cases are impossible narrow-zone edge setup, missing-edge contact, ordinary
contained setup, and a base outside a wide zone where it could fit elsewhere.
The base rejects/accepts `[false, false, true, false]`; head returns
`[true, false, true, false]` in all seven samples.

Base is `1fea43187c920d5a13f6af25ce55ba0c67608fe7`. Head's reviewed engine identity is
`warhammer40k-core-v2:runtime-tree-sha256-v1:9075f96cf617e83e79dfadc7e94ca4866fb446f7770f2bcabbe5088e9ae371c9`.
`base.json` and `head.json` retain CPU, RAM, OS, interpreter, lockfile and identical
workload/helper hashes, per-sample wall time, cold first sample and cache boundary.
The benchmark excludes fixture construction and runs serially on the same host.

Mean per four resolutions: **1.55 ms base, 3.80 ms head**. Maximum:
**1.92 ms base, 17.36 ms head**. The predeclared component budget is head mean at
most three times base plus 50 ms, and maximum below one second; both pass.
This is component evidence only. Gameplay-slice and complete-game throughput
were not measured, and the standing 60-second mean/300-second maximum full-game
targets are not certified by these results. Order 32's deferred broader budgets
remain deferred. No timeout or unresolved computation is accepted as a rules answer.

Reproduce with the same benchmark/helper files over base and head runtime trees:

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_order54.py \
  --output docs/performance/order54/head.json --revision <reviewed-revision>
```

The base archive uses the same existing virtual environment with its own `src`
first on `PYTHONPATH`. Both runs need access to macOS `sysctl` for hardware
identity. Static quality tests verify matched inputs, expected results and budgets.

## Composite-region review repair

The repair of the P2 finding in `6ae47595` replaces syntactic polygon-set
absorption with exact quantifier-free containment in the union of the remaining
regions. The matched v2 workload retains the original four cases and adds a
canonical 200 mm model outside a square zone, both alone and with an equivalent
two-rectangle region containing a circular cutout. Base accepts the redundant
case incorrectly; head rejects both out-of-zone proposals. All other outcomes
remain the same.

`review-base.json` records commit `6ae47595078afd49c9a61bc4b06d20b18ebe14a8`;
`review-head.json` records corrected engine identity
`warhammer40k-core-v2:runtime-tree-sha256-v1:201fb73e0edba77c9d234b7c0f7a174b548c2907f01a28c4e8092e01a511ba3e`.
The six resolutions average **15.54 ms base, 5.28 ms head**, with maxima
**93.83 ms base, 22.11 ms head** across seven samples. Both unchanged component
budgets pass. Reports retain matching workload/helper hashes and host metadata;
runs were sequential with no competing test workers. The host remains
provisional. These results do not certify gameplay-slice or full-game throughput.
Reproduce using the command above with `--composite` over both runtime trees.

## Initial validation at 6ae47595

Validation against the initial engine identity passed:

- Complete behavioral suite with xdist work stealing and coverage: **8,250
  passed**, **85.11% coverage**, 635.83 seconds. Ten existing SQLite resource
  warnings did not fail the run. No second uncovered behavioral gate was run.
- Complete code-quality suite with xdist work stealing and no coverage:
  **506 passed**, 117.81 seconds.
- Ruff lint/format, mypy (3,076 files), Pyright, all 11 import contracts, and
  `uv run pre-commit run --all-files` passed.
- Source generator, engine identity, external-contract generation with the base
  ref above, and the exact eight-shard inventory check passed. The shards were
  regenerated from the successful covered run's JUnit profile.
- TypeScript generated-client/type checks and five unit tests passed;
  conformance passed all 342 assertions for contract 25.0.0. The installed wheel
  passed with 2,840 engine resources and 27 contract schemas.

The quality audit inventories include the new source package. The existing
Rapid Ingress work metric now identifies the public resolver by its code object,
so the extracted implementation is not counted as a second resolution. Its
budget remains unchanged, and the placement audit requires exactly one call.

Focused geometry, deployment, reserves, source, activity-lock, stale-choice,
restore/replay and quality regressions also passed for that initial tree.

The final coverage command uses `COVERAGE_FILE=/tmp/order54-final-coverage/.coverage`
to isolate its SQLite output. The shared repository `.coverage` report initially
failed with `unable to open database file`; the collected data was subsequently
readable and passed the threshold. The isolated final run is the delivery gate
and the source of the committed shard timing profile. Node is supplied through
the required Codex runtime `PATH` prefix; npm uses the existing pyright nodeenv.

## Review repair validation

The corrected runtime identity `201fb73e0edba77c9d234b7c0f7a174b548c2907f01a28c4e8092e01a511ba3e`
passed the complete behavioral gate: **8,256 tests**, **85.11% coverage**, 610.21
seconds, with ten existing SQLite resource warnings. The run used xdist work
stealing, the required Node PATH prefix, and isolated
`COVERAGE_FILE=/tmp/order54-review-coverage/.coverage`. Its successful JUnit
profile regenerated all eight shards; the exact inventory check passed.
The subsequent complete code-quality suite passed **507 tests** in 116.90
seconds with xdist work stealing and no coverage.

All 69 focused geometry/deployment/activity regressions and 17 projection tests
passed. Ruff lint/format, mypy, Pyright, all 11 import contracts and pre-commit
passed. Source and engine-identity checks, external contract checks against the
PR base, installed-wheel smoke, generated TypeScript/type checks, five client
unit tests and all 342 conformance assertions passed. The runtime tree remained
unchanged after the successful covered run.
