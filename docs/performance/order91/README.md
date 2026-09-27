# Order 91 performance and validation

The matched `order91-shooting-selection-v1` workload compares base `cacde87c`
with Order 91 using identical script, fixture and dependency hashes. Five serial
samples per case run without coverage or competing test/build workers on the
provisional Apple M5 Pro / 64 GiB host. The boundary includes both ordinary unit
eligibility and type eligibility; catalog/facade restoration setup is recorded
separately. Reports retain every sample, counts, summary and runtime identity.

| Case | Base mean (ms) | Head mean (ms) | Eligible unit/type counts: base → head |
|---|---:|---:|---|
| No ranged weapons | 0.447 | 0.346 | 0/0 → 1/1 |
| All targets out of range | 0.506 | 0.207 | 0/0 → 1/1 |
| Reachable target | 0.792 | 0.206 | 1/1 → 1/1 |

The changed work counts demonstrate the repaired eligibility, while the reachable
case preserves its result. All cases use one friendly and one enemy infantry model,
20 inches apart with no terrain. These small samples are diagnostics, not a timing
budget or certification. No unrelated optimization was added.

Reproduce:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order91_shooting.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order91_shooting.py --output /tmp/head.json
```

Inherited runtime-pinned diagnostics retain historical baselines, workloads,
work assertions and numeric budgets. Current head reports are refreshed through
commands recorded in `inherited-refresh.json`. Owner-deferred component budgets
remain deferred. Complete-game samples are zero; complete-game mean, maximum and
certification remain unknown.

The independent code review found one Indirect eligibility gap: destroyed weapon
bearers were included and live keyword effects were ignored. Both consumers now
use the shared living/retained, effect-aware weapon inventory, retaining spent
One Shot weapons only for possession checks. Direct regressions cover both cases.
The reviewer rechecked the repair and approved the code with no remaining findings.

An initial aggregate run was interrupted to diagnose 119 failures from obsolete
auto-skip fixture assumptions and replay-history validation. The fixtures now select
the existing phase-completion option, terminal replay permits the lifecycle’s
paired-null completed-game boundary, and out-of-phase hosts require an already
accepted source decision. All 119 affected tests passed in focused retests. The
independent reviewer approved these repairs before final validation. The interrupted
run is retained as diagnostic evidence, not a successful final coverage gate.

A subsequent complete run reached 85.16% coverage with 9,521 passing tests and
two obsolete expectations: Normal Shooting was hidden without visible targets,
and Explosives skipped targetless Shooting. Those assertions were corrected while
retaining invalid-declaration, damage and replay checks. Both focused retests passed
and independent review approved the changes. Runtime code and performance input
hashes did not change.

The final behavioral run passed all **9,523 tests** with **85.16% branch-inclusive
coverage** (727.85 seconds), followed by all **696 code-quality tests** without
coverage (113.58 seconds). The first quality run exposed two obsolete structural
assertions, updated to enforce the new rules-unit type selector and the shared
empty-completion-to-retained-cleanup path. Focused checks and independent review
approved those audit-only edits before the successful quality rerun.

Ruff check/format, mypy, pyright, all 11 import contracts, source-actions generation,
engine identity, external contract against the exact base, installed-wheel smoke,
TypeScript check, five TypeScript unit tests, and all 342 HTTP conformance assertions
passed. The successful complete JUnit profile regenerated the eight-shard inventory;
the exact shard check and all-file pre-commit checks passed. Runtime code was not
changed after the successful behavioral gate.

[Machine-readable validation](validation.json) records the exact runtime/base,
commands, exit codes, timings, artifact/log hashes, prior diagnostic attempts and
performance limitations. The independently reviewed implementation and all repair
rounds have no outstanding code findings; the final staged delivery also receives
independent evidence review before push.
