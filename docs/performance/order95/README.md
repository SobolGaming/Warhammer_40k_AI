# Order 95 performance and validation

The matched `order95-optional-shooting-v1` workload compares base `185d7c55`
with the completed implementation using the same script, fixture and dependency
hashes. Five serial samples per case run without coverage or competing test/build
workers on the provisional Apple M5 Pro / 64 GiB host. The base is an archived
read-only source snapshot, measured after implementation on the same environment.
Timing covers facade declaration submission through completion, with setup and
authenticated restoration reported separately.

| Case | Completion mean (ms) | Restore mean (ms) | Ranged history / One Shot records |
|---|---:|---:|---:|
| Base targeted | 75.651 | 265.277 | 1 / 1 |
| Head targeted | 73.931 | 266.019 | 1 / 1 |
| Head targetless | 15.792 | 258.036 | 0 / 1 |
| Head empty | 7.767 | 256.340 | 0 / 0 |

The workload uses two friendly single-model units, one enemy and no terrain.
The targetless and empty cases directly demonstrate independent weapon selection
and actual attack participation. They are new head-only paths, not base/head
speedup comparisons. These finite slice diagnostics do not certify complete games.
No complete head-to-head games were measured; full-game mean and maximum remain
unknown. Owner-deferred provisional component gates remain deferred.

Reproduce serially:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order95_shooting.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order95_shooting.py --output /tmp/head.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order95_shooting.py --new-paths --output /tmp/new-paths.json
```

Inherited runtime-bound head reports are refreshed with the exact commands,
elapsed times and hashes in `inherited-refresh.json`. Historical baselines,
workload assertions and numeric budgets remain unchanged. The Firing Deck
restriction fixture adds its spare shooter in a new named helper, preserving
the original matched Order 65 and Order 70 benchmark fixture and its committed hash.
Both reports were re-measured after restoring that shared fixture. The initial
quality run caught the still-stale Order 70 report; its focused three-test quality
check passed after remeasurement. Superseded measurements remain explicitly marked
in the refresh record, with historical baselines and budgets unchanged.

Independent review found and repaired skipped mandatory selected-unit consequences
and incomplete empty-declaration restoration authority. The same-class search
included the generic Shadow Legion registration and automatic no-candidate
completion. The second independent review approved the implementation with no
remaining findings; its six-test reproduction subset passed. The 107-test focused
suite also passed, followed by the source-loaded Shadow Legion registration check.

The final independent publication review approved the complete diff and verified
all 25 inherited report hashes and runtime identities. Contract 42 base-ref
compatibility and installed-wheel smoke checks passed. The generated TypeScript
client check, type check, six unit tests and 342 HTTP conformance assertions passed.
The bundled runtime contains Node but no npm executable, so those package scripts
were executed through their identical Node CLI entry points, recorded below.

The first aggregate run passed 9,795 tests with three failures and reached 85.21%
coverage. Repairs were confined to tests: a schema-specific TypeScript check moved
out of the generic interaction gate, one restore assertion adopted the earlier
precise rejection, and cargo-drift fixtures now place removed passengers instead
of leaving living models unaccounted for. The reviewer independently confirmed
valid cargo drift still returns a typed invalid result without mutation, then
approved all three repairs. All 22 focused regressions, six TypeScript unit tests
and static gates passed afterward. The runtime and benchmark evidence did not change.

The exact required gate commands, results, timings and log hashes are recorded in
[validation.json](validation.json). Failed iterative checks remain in that record
as diagnostics; the final successful results determine delivery status.

Final gates passed: **9,798 behavioral tests**, **85.21% coverage**, and
**764 code-quality tests** without coverage. All eight shard manifests were
regenerated from the final passing JUnit profile and the exact fail-closed inventory
check passed. Ruff, formatting, mypy, pyright, import boundaries, pre-commit,
generated artifacts, base-ref compatibility, package smoke and client checks passed.
The independent reviewer approved the final corrected evidence with no open findings.
