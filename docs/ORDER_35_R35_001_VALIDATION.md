# R35-001 — discounted Rapid Ingress restoration

The independent review found that a valid pending Rapid Ingress target request
at 0 CP failed restoration despite an active automatic target discount. R35-001
is reproduced and repaired. Independent review of the repaired SHA remains
required; this author validation does not approve or merge PR #441.

## Invariant and repair

An engine-issued pending target request must survive JSON checkpoint restoration
when a legal target remains affordable under active runtime cost modifiers.

The reviewed head called `_stratagem_unavailable_reason` without a modifier
registry or a selected target. It charged the printed 1 CP during restoration,
where live request creation and submission correctly accepted the discounted
0 CP use. Passing only the registry would still miss target-dependent discounts.

`GameLifecycle.from_payload` now rebuilds its runtime bundle before pending
battlefield validation, and explicitly passes the active cost-modifier registry
through the existing consistency owner. Rapid Ingress restoration delegates to
the same `_parameterized_stratagem_unavailable_reason` service and preflight mode
used by live request creation. No cost arithmetic or target enumeration is
duplicated. Provenance, timing, round, keywords, restrictions and placement-use
checks remain mandatory. No new decision or payload shape is introduced; the
[adapter contract](ADAPTER_DECISION_CONTRACT.md) records this correction.

The same-class search inspected affordability calls in engine authority and
consistency modules and both callers of the pending-validation chain. Only the
Rapid Ingress target checkpoint had this defect. Accepted placement restoration
already authenticates its recorded use and remains unchanged. The production
repair is confined to three existing restoration modules; generated changes
refresh runtime fingerprints and their contract/example hashes. Source rules,
semantic-support classification, handler inventory and geometry are unchanged.

## Regression evidence

The added catalog fixture compiles an automatic per-target discount into real
RuleIR, then loads it through the normal runtime bundle. It uses no manually
injected registry or engine integration stub.

- Before the fix: both discounted-player cases failed with
  `insufficient_command_points`; four ordinary-cost/negative controls passed.
- After the fix: 70 focused behavioral, static and work-budget checks passed.
- Both players are covered at 0 CP through engine-issued request creation,
  standalone JSON restoration, session persistence, exact replay, both-viewer
  projections and event deltas, live/restored target submission equality,
  recorded 0 CP cost and modifier identity, placement and parent continuation.
- Both players' unaffordable checkpoints without a discount still fail closed.
- A narrow AST audit prevents the pending authority from returning to unbound
  affordability or omitting its active modifier registry.

## Tested identity

- PR base: `42760e107d361f30bdf19b5d9fa6c2cc67fb9c7a`.
- Reviewed, defective head: `3ab4f45c2ce3de2c1453c597cba91ff642c5da19`.
- Repair and aggregate-tested commit: `031bdd5e59b3ce46ef5bcc5f03e25d685517402a`.
- Repair tree: `f6ba09dec4dc0d7e6f5565e6e4e6950eedd6999e`.
- Source tree: `217a7d7f885b1b3cde30a41011491b534b4ddf25`.
- Test tree: `d5ec9640e45bd89ae4cf31e0e572be873648a7e0`.
- Script tree: `8ee818ca305ed4acab451ca4e31acf2f09ad1018`.
- Contract tree: `4a0f294cec98a8001bc324bcb7316dfb80a9a6c4`.

The 70-test focused run preceded only a private-import type-check annotation
and its generated identity refresh. Final aggregate gates run on the repair
commit above. The subsequent evidence commit must preserve all four listed
source/test/script/contract trees; those identities are checked before push.

## Final local gates

| Gate | Result |
|---|---|
| Complete behavioral suite, once with coverage | 6,982 passed; combined command exit 1 due to coverage-report database error (494.405 s) |
| Saved behavioral coverage report and 85% gate | 85.05%; exit 0; reporting recovered without rerunning tests |
| Complete code-quality suite, without coverage | 417 passed; exit 0; 106.648 s |
| Ruff check / format, mypy / Pyright | Passed; exit 0; 2,825 files type-checked |
| Shard inventory / import boundaries / pre-commit | Passed; exit 0; all 11 import contracts kept |
| Core Stratagem / Movement source and runtime identity checks | Passed; exit 0 |
| External contract against exact PR base / installed wheel | Passed; exit 0; 27 schemas and 2,638 runtime resources |
| Generated TypeScript client / unit tests | Passed; exit 0; 5 unit tests |
| Live TypeScript conformance | Passed; exit 0; 342 assertions and replay equivalence |
| Scoped performance comparison | Passed; exit 0; unchanged budgets |

## Performance

Seven uninstrumented samples per scoped case compare the reviewed head with the
repair on the same provisional Apple M5 Pro host, Python 3.14.5, lockfile and
final fixture/script inputs. The reviewed-head worktree receives only the new
test helper; its runtime is unchanged. Timings run without competing test
workers. All existing mean, maximum and work budgets are preserved.

| Scoped slice | Reviewed head mean ms | Repair mean ms |
|---|---:|---:|
| Legal availability and target submission | 11.296 | 10.764 |
| First-round rejection | 0.032 | 0.031 |
| AIRCRAFT rejection | 0.092 | 0.086 |
| Mixed 16-unit reserve inventory | 69.123 | 62.995 |
| Placement and parent continuation | 122.045 | 119.104 |

The existing comparison script passes all five cases using the unchanged
`budgets.json`. A separate diagnostic measures `GameLifecycle.from_payload`
against a prepared JSON checkpoint: ordinary restoration mean 313.301 →
311.704 ms; discounted restoration mean 311.647 ms on the repair, with all
seven samples successful. The defective head rejects all seven discounted
samples early, so its 34.346 ms rejection time is not a successful-restoration
performance baseline. These restoration diagnostics introduce no new budget
or full-game claim. Full-game certification remains outstanding.

## Command evidence and review status

Command identities, working directories, UTC start times, deadlines, process
IDs, terminal exits and durations are retained with raw logs. The existing
Order 35 command supervisor was reused. The deliberate red run, the initial
post-fix runtime-fingerprint collection rejection, and two fixture/import
annotation failures are retained alongside the successful final commands.
No timeout, hung process, weakened check or redundant final no-coverage
behavioral suite was used.

The behavioral run collected coverage but its final reporter could not open
`.coverage`, incorrectly displaying 0.00% and exiting 1 after all 6,982 tests
passed. The saved SQLite coverage database passes `PRAGMA integrity_check` and
contains 2,499 measured files and 451,916 arc rows. Standalone
`uv run coverage report --show-missing --fail-under=85` succeeds on that same
database (exit 0); a total report records 85.05%. The database and its SHA-256
are retained with the evidence. The original combined command is recorded as
failed, not relabeled successful, and the behavioral suite was not repeated.

The final measurement JSON, command manifest and runnable diagnostic scripts
are retained in [the R35-001 evidence directory](performance/order35/r35-001/).
`command-evidence.tar.gz` includes raw logs, JUnit reports, the unchanged
supervisor, and the restoration/comparison scripts. To repeat the focused
regressions and CI work audit:

```sh
uv run pytest tests/unit/test_phase12c_core_stratagems.py tests/code_quality/test_order35_rapid_ingress_work.py -q -k 'order35 or rapid_ingress' --no-cov
```

The previous full CI result applies only to reviewed head `3ab4f45c`; it does
not validate this repair. CI and independent review of the newly published head
remain separate from local validation.

The repair request arrived at 12:05:24.633 UTC on 2026-09-10. The repair commit
was created at 12:14:44 UTC (9.3 minutes including focused reproduction and
initial measurements). Final aggregate validation began at 12:17:40 UTC after
the matching final performance comparison and scope audit. Command durations
overlap where independent checks run concurrently.
The behavioral process completed at approximately 12:25:55 UTC; coverage
recovery started at 12:51:27 UTC. This 25.5-minute dispatch gap is included in
wall-clock elapsed time; its cause is not established by the process evidence.
All final local checks completed at approximately 12:54:05 UTC, 48.7 minutes
after the repair request including that gap. Publication follows these gates;
there was no deliberate wait for external CI or independent review during the
repair validation. Focused test commands totaled 122.1 seconds, overlapping
implementation; the final behavioral and quality processes totaled 601.1
seconds. No production change followed the aggregate-tested repair commit.
