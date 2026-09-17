# Order 54 performance and delivery evidence

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

## Validation

Final validation against the engine identity above passed:

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
restore/replay and quality regressions also passed. The final runtime tree did
not change after the successful covered run.

The final coverage command uses `COVERAGE_FILE=/tmp/order54-final-coverage/.coverage`
to isolate its SQLite output. The shared repository `.coverage` report initially
failed with `unable to open database file`; the collected data was subsequently
readable and passed the threshold. The isolated final run is the delivery gate
and the source of the committed shard timing profile. Node is supplied through
the required Codex runtime `PATH` prefix; npm uses the existing pyright nodeenv.
