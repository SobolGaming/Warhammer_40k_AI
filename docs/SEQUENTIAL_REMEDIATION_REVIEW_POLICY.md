# Approved review policy for subsequent remediation orders

The repository owner approved this policy on 30 September 2026 during Order101.
It applies to subsequent orders, beginning with `THROUGHPUT-AFTER-101`, then
Order102 onward. Order101 finishes under its existing acceptance and review gates.

Prioritize complete playable rules and faction support. This priority does not
expand an order's authorized implementation scope, authorize prohibited content,
or present load-only faction content as implemented gameplay.

## Blocking findings

Block on incorrect rules, normal legal gameplay failures, and save/load or replay
failures reproducible from engine-generated valid state. Explicitly required
trust-boundary failures also block. Every blocking finding must state:

1. The reproduced entry path and exact reviewed head.
2. The concrete user impact.
3. Whether normal engine-generated state reaches the failure, including evidence
   and any unproven step.
4. The violated order acceptance requirement or explicitly required supported-input
   boundary.

A source suspicion or hypothetical attack is not a reproduced normal-play defect.
Distinguish incorrect rules, normal gameplay, genuine save/load/replay, supported
input validation, and manually modified historical state in the report.

## Separately queued work

Queue deeper tamper resistance and coordinated hand-edited-history findings as
separate integrity-hardening work when no normal path or necessary supported-input
boundary is demonstrated. Preserve the reproduction and evidence without claiming
the queued issue is fixed or that snapshot integrity is universally certified.
The queue is not authorization to implement or merge that work silently.

Keep review focused on the order's acceptance criteria and affected behavior.
Expanding implementation or blocking scope requires an explicit decision. A
reviewer must identify the new scope and why the current acceptance requirement
cannot be completed locally before asking for expansion.

## Unchanged delivery gates

Preserve required regression tests, positive legal-path controls, truthful source
evidence, shared engine authority and exact-head validation. This approval removes
neither the complete local covered behavioral gate nor complete remote CI. Both
type checkers, all other applicable quality/generated/contract/package gates,
required behavior shards and coverage thresholds remain mandatory.

Independent coding and fresh parent Astra reviews must be clean under this scoped
policy on the exact final head. Any subsequent change invalidates stale reviews
and applicable evidence. This policy grants no merge authorization by itself.

## Required prompt text

Include the following in each subsequent implementation/reviewer prompt and parent
Astra audit packet, together with the order's explicit acceptance criteria:

> Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
> playable behavior in this order. Block on incorrect rules, normal legal-play
> failures, engine-generated valid-state save/load/replay failures, and explicitly
> required trust-boundary failures. For each blocker provide the reproduced entry
> path, impact, normal reachability and violated acceptance requirement. Queue
> coordinated hand-edited-history hardening separately when no necessary supported
> input boundary or normal path is demonstrated. Keep scope within this order;
> expansion requires an explicit decision. Preserve positive controls, regression
> tests, source truthfulness and every required local/remote exact-head gate.

The author must give reviewers the selected source obligations, affected owners,
consumer paths, supported input boundaries, pending checks and exact base/head.
Reviewers derive requirements from that evidence rather than treating the author's
conclusions as approval.

## Subsequent-order model plan and evaluation

The owner's subsequent direction supersedes the earlier Sol High/Ultra plan:
explicitly select GPT-6 Astra (`gpt-6-astra`) with High (`high`) for
implementation and separate independent coding review, beginning with
`THROUGHPUT-AFTER-101`. Preserve the additional fresh parent Astra audit and
its exact-head verdict; an author's or coding reviewer's selection does not
satisfy that separate audit. Stop rather than silently substitute a model.

Verify accepted explicit model/effort selection and retain any limit on resolved
runtime attestation. Do not silently substitute a model or claim effort tiers have
independent capacity. No measured speed or quality advantage is asserted here.

The owner updated this workflow on 2 October 2026 after Order 103: High replaces
Extra High; use the requested 1.5x speed when the execution environment exposes
that control, without claiming an unavailable runtime setting. Use one
implementation/review cycle with necessary fixes. Run the independent coding
review alongside validation and the fresh parent audit alongside hosted CI.
Keep automatic evidence capture off the critical path; archive transfers are not
publication prerequisites. Do not add repeated intermediate planning, benchmark,
or evidence reviews. Preserve both clean exact-head reviews, complete correctness
inventories, local covered behavior at 85%, quality/type/lint/contracts, required
hosted CI and branch protections.

For these bounded repairs, the default performance evidence is the existing
serial current-runtime smoke and exact-base assessment. Detailed benchmarks are
required for deliberate performance changes or a demonstrated serious regression.
Preserve historical measurements and live semantic/work/cache checks. This
owner direction supersedes broader comparison defaults, without extending the
Order 103-only numerical exception or claiming full-game performance certification.

For the next few orders, retain timestamped phase transitions and actual command
durations, review findings and their normal reachability, repair/revalidation
cycles, invalidated evidence, interruptions and first/final head identities. Track
elapsed time and rework separately. Concurrent command sums are not wall time;
unknown active time remains unknown. Evaluate measured results before claiming a
throughput or quality improvement from this model plan.
