# R93-001 permission-context repair

The invariant is that permission restrictions use the actual attack occurrence
and subject role when the request is created and when a choice is validated.
The reviewed head `d0f6e96d` instead used a unit-only, attacker-role lookup for
persisted grants. This could discard selected-target and defensive permissions.

The pre-repair baseline is an immutable archive of that reviewed head, measured
before production edits. It uses the unchanged Order 93 benchmark, dependency
lock and provisional host. The existing no-permission attack allowance remains
`head mean <= base mean * 1.25 + 0.05 seconds` for each phase, with unchanged
attack/decision counts. The thirteen-operation Charge diagnostic measures the
existing bounded choice path separately. Timings run serially without coverage
or competing test/build workers. Full-game targets remain unverified.

The repair carries typed attacker, target, subject-role, phase, weapon and
available Strength/Toughness evidence through attack modifier owners and their
shared before-pop permission validation. Historical reconstruction authenticates
that evidence. A restriction requiring attack facts unavailable at an earlier
boundary must produce an explicit unsupported diagnostic; an omitted fact must
never silently disable a supported permission.

Defensive source-unit Starting/Half Strength conditions remain explicitly
unsupported until source ownership can be authenticated separately. Independent
review reproduced both erroneous outcomes: a damaged defender with a healthy
attacker lost its permission, and a healthy defender with a damaged attacker
received it. Four opposite-health regressions first failed, then passed with the
typed unsupported classification. Attacker-specific ability/charge predicates
retain their existing meaning; keyword predicates remain scoped to the subject
role. No new descriptor families or content support are claimed.

Before this repair, six of nine initial facade cases failed on the reviewed head.
All thirteen final cases now pass through `LocalGameSession`: matching and
nonmatching selected targets, attacker/defender and wrong-role cases, real
Strength/Toughness comparisons, context tampering before queue pop, owner/opponent
redaction, pending/completed restoration and exact replay. Fourteen additional
direct tests cover typed payload validation, model ownership, unsupported
descriptors and missing facts. Existing attack and neighboring modifier suites
also passed during iteration.

The independent reviewer approved the code and architecture after the defensive
source-strength correction. Current-runtime aggregate validation passed:
9,756 behavioral tests with 85.203379% branch-inclusive coverage, followed by
705 code-quality tests without coverage, both using eighteen xdist work-stealing
workers. The eight-shard inventory was regenerated from that complete successful
behavioral profile. Required lint, format, type, import, pre-commit, generator,
base-ref contract, TypeScript, HTTP conformance and installed-wheel checks also
passed. `validation.json` records commands, results and evidence hashes, with
final independent publication approval recorded separately from code approval.
The reviewer returned **APPROVE for publication**, with no remaining actionable
findings, after verifying the final gates, artifacts, shards and performance
evidence and before the repair commit/push.

## Matched performance

The final runtime is
`warhammer40k-core-v2:runtime-tree-sha256-v1:699ca0e11f45466d9a7d0c16706fde3562d231d7856d7d70bbe2ef6b4a994e75`.
`comparison.json` verifies identical script, fixture, lock, host and workload
metadata against the pre-edit baseline, with five measured runs after one
warmup for each phase.

| Slice | Reviewed head mean | Repaired head mean | Unchanged allowance | Result |
| --- | ---: | ---: | ---: | --- |
| Shooting | 0.2664 s | 0.2643 s | 0.3830 s | Pass |
| Fight | 0.1558 s | 0.1556 s | 0.2448 s | Pass |

Both phases preserve all attack/decision counts and emit no general modifier
choices. The thirteen-operation Charge diagnostic averages 5.45995 s before
the repair and 5.43569 s afterward, with a repaired maximum of 5.44339 s. All
three samples preserve thirteen accepted choices and at most four options per
request. No Charge timing budget or full-game certification is inferred. The
unchanged benchmark's `head-only` status text describes the original Order 93
base; both revisions in this repair comparison already support that path.

The inherited refresh records actual reruns of the twenty-five required runtime
diagnostics in `inherited-refresh.json`. Original baselines, fixture proofs and
numeric budgets remain unchanged. Older Order 93 reports remain historical.
