# Order 35 / P15G / C15-07 — author validation

[PR #441](https://github.com/SobolGaming/Warhammer_40k_AI/pull/441) repairs Rapid
Ingress eligibility. All required local gates passed. Full CI on the final
published head and owner-initiated independent review remain separate, outstanding
requirements. The author has neither approved nor merged this PR.

## Source and scope

The [source → invariant → consumer → regression matrix](ORDER_35_SCOPE_PLAN.md)
records the complete approved 15.07 source, historical hashes and applicable
20.04 placement requirements. Those artifacts, provenance hashes and partial
semantic-support classification are preserved.

The repair shares authoritative round, Strategic Reserve and current model-owned
AIRCRAFT eligibility across availability, canonical target enumeration, finite and
parameterized preflight, and pending placement. It closes changed-context and
pending-origin bypasses through existing decision/use provenance. Existing cost,
Battle-shock, use limits, geometry, placement retries, parent continuation,
viewer redaction and independently authorized first-round Ingress remain owned
by their existing services. No new ledger, handler family or geometry system is
introduced. Shared test fixtures were extracted; old Rapid Ingress fixtures now
use actual Strategic Reserves and legal placement locations.

The pre-fix source matrix reproduced 12 failures with 6 passing cases. The
published candidate passed 57 focused regressions. A further 18-test audit
(overlapping existing cases) passed coordinated request/event corruption and
performance checks. Valid target, placement and arrival checkpoints exercise
standalone restoration, JSON persistence, exact replay and both-viewer deltas.

## Exact validated identity

- Base: `42760e107d361f30bdf19b5d9fa6c2cc67fb9c7a`.
- Aggregate-tested commit: `7af71751572ee6dea3bfebcf8c9ae36304ee516c`.
- Tested tree: `1c66a966461306e0a90990d9d6d95150b45aa7bb`.
- Source tree: `5d7b104cd9c093400e9f51291f078431a4fb873d`.
- Test tree: `0d06c6fc7c68d17218509ec26266e162db388c8a`.
- Script tree: `8ee818ca305ed4acab451ca4e31acf2f09ad1018`.
- Contract tree: `8f56d0bbda715727d1f844ef2f2364c018f20880`.

The subsequent handoff commit contains documentation/evidence only. The source,
test, script and contract trees above must remain identical; this is checked
before its push. Final timing/profile inputs match all seven recorded lock,
script and helper hashes. Their recorded head `a1d8a0456bc4de1763b0934d3c80d51a44eb71b8`
has the same source tree as the aggregate-tested commit; the final benchmark
inputs are authenticated independently by their content hashes.

## Local gates and actual outcomes

| Gate | Result |
|---|---|
| Full behavioral suite, once with coverage, 18 xdist work-stealing workers | 6,978 passed; 85.05% coverage; exit 0; process 527.390 s |
| Full code-quality suite, once without coverage, 18 workers | 416 passed; exit 0; process 107.391 s |
| Ruff check / format check | Passed, exit 0 |
| mypy / Pyright | Passed, exit 0; mypy checked 2,825 source files |
| Eight-shard fail-closed inventory check | Passed, exit 0; no behavioral test-file addition/move |
| Import boundaries / pre-commit all files | Passed, exit 0; all 11 import contracts kept |
| Core Stratagem / Movement source generators, `--check` | Passed, exit 0 |
| Runtime identity / external contract with exact base ref | Passed, exit 0 |
| Installed wheel smoke | Passed, exit 0; 27 schemas, 2,638 runtime resources |
| Generated TypeScript client / client unit tests | Passed, exit 0; 5 unit tests |
| Live TypeScript conformance and replay equivalence | Passed, exit 0; 342 assertions |
| Scoped performance comparison / CI work gate | Passed, exit 0 |

Exact commands, cwd, UTC starts, deadlines, PIDs, exits and process durations are
in [validation.json](performance/order35/validation.json). Raw logs, JUnit results,
command metadata, process samples and the reused Order 34 supervisor are in
[command-evidence.tar.gz](performance/order35/command-evidence.tar.gz).

The initial contract/client command exited 127 only after the Python contract
check and wheel smoke had completed successfully: this shell lacked `npm`.
Only the unrun client steps were resumed, using the existing Order 33/34 npm
runtime; the resumed command exited 0. No completed behavioral suite was repeated
without coverage. No production change followed the aggregate run's start.

## Performance, CI and review limits

The [performance report](performance/order35/README.md) retains every base/head
sample, work count, input hash and numeric budget. Legal selection/submission
mean is 10.699 ms (-0.2%); mixed inventory 72.278 ms (+6.1%); placement and parent
resume 117.119 ms (-2.7%). Reserve-list queries stay at 10 for one and sixteen
units; excluded requests initiate no geometry. All declared budgets pass.
Component results do not certify the standing full-game targets; a complete
supported head-to-head workload/driver remains outstanding.

The early draft was published at 03:40 UTC with the explicitly authorized
pending gates. Its CI skipped behavior/coverage and failed the stale generated
contract plus dependent quality summary. The refreshed contract is committed
and passes locally. The ready-for-review transition triggers full CI for the
final head; a green draft is not full validation. Independent review is pending
and must apply to the final reviewed SHA.

Task start was approximately 02:43 UTC on 2026-09-10; all local gates completed
at 04:00:04.914 UTC, about 77.1 minutes later. Before aggregate validation,
implementation/scoping/benchmarking occupied approximately 60 minutes and focused
commands 6.0 minutes. Baseline/performance commands totaled 2.7 minutes within that
implementation interval. Final aggregate wall time was 10.8 minutes; typing and
client checks overlapped it. Draft publication took 5.811 seconds. There was no
dedicated wait for external CI or independent review. Final documentation and
publication add a few minutes to the handoff time.

Early fixture, annotation and runtime-manifest mismatches were repaired in
focused iterations. A slower focused run and quiet conformance run were checked
with bounded process diagnostics; both exited normally within their deadlines.
No timeout, abandoned live process, or user intervention was required.
