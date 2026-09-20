# Order 64 / P20B: reserve defaults and lifetimes

Status: implemented and locally validated on 2026-09-19. Base: `d3a9d3b4`
(Order 63, PR #483).

The violated invariant is that reserve eligibility, cleanup and movement/effect
lifetimes must use current Core rules and the same authenticated state for every
adapter. The prior Core default permitted first-round Deep Strike and postponed
reserve destruction until battle end. Round-three and final-turn cleanup are
separate obligations, with different exemptions.

## Authority and scope

The complete 20.01.02, 20.02, 20.03 and 20.04 text was observed in
[40k.app](https://www.40k.app/rules/20-strategic-reserves) on 2026-09-19 at 21:33 UTC
(minute precision). This is an owner-authorized maintained App-data mirror, not
official GW. The reviewed JSON preserves per-rule transcription hashes and
observation fingerprints. Historical official Core Rules PDF provenance remains
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

The end-to-end owners are source/mission policy -> reserve declaration and
source-authorized departure -> shared ingress proposal and placement resolver ->
accepted phase movement history -> move eligibility/validation -> round and final
turn boundaries -> destruction evidence, projections, save/restore and replay.

- Core arrival starts in round two; Core unarrived reserves expire in round three.
- Accepted ingress history and actual battlefield departure history identify the
  ingress and repositioning exemptions. A during-battle origin alone does not
  establish that a newly created unit was repositioned. Cargo follows its carrier's
  reserve route and cannot independently arrive.
- Final-turn cleanup applies independently of round-three exemptions and does not
  invoke destroyed-model reactions. Terminal state records its actual boundary.
- Ingress locks every other movement type until the next Charge phase starts.
  Ordinary, reactive, Charge and Fight movement use shared checks. Set-up moves
  retain their explicit placement validation; witnessed moves retain PathWitness.
- Repositioning preserves Advance/Fall Back/Disembark history and timed effects;
  spatial effects continue to be evaluated against current presence and geometry.
- Source-bound mission overrides retain their identity. Arbitrary custom deadline
  policy is never attributed to Chapter Approved merely because it uses round three.

## Additional performance guard

The user explicitly requested a dedicated post-ingress reconstruction guard. The
versioned workload measures `GameLifecycle.from_payload` and `LocalGameSession.fork`
separately after loaded ingress, Rapid Disembark and a later accepted decision.
Preparation is excluded; fork serialization/deepcopy is included. Independent
profile runs count replay passes, lifecycle constructions, replayed submissions and
placement resolutions. Exact authentication remains mandatory.

Matched base/head timings run serially without coverage or concurrent test workers
on the same provisional host and dependency lock. CI enforces work budgets and
checks retained timing comparisons. These component results do not certify
gameplay slices or complete games, and add no search/training implementation.

## Validation and scope audit

The clause regressions use existing source-backed providers and real typed state:

| Obligation | Owning regression evidence |
| --- | --- |
| Core arrival minimum and explicit overrides | `test_phase10p_reserves.py` validates first-round rejection and later ingress; the existing Realm of Chaos source-bound arrival path retains its explicit timing override. |
| Round-three ingress, cargo and repositioning exemptions | `test_order64_reserve_lifetimes.py` covers carrier/cargo routes and rejects origin-only invented exemptions; `test_phase17g_chaos_daemons_daemonic_incursion.py` restores authenticated departures with and without prior ingress. |
| Independent final-turn cleanup | Order 64 boundary tests cover carrier/cargo destruction without model-destroyed reactions, exemptions ending at the final boundary, and terminal boundary validation. Existing Primary timeline and cargo cleanup regressions retain source provenance. |
| Already-moved repositioning and same-turn history | Real Advance/Fall Back records survive the generic source removal path; the Gate of Infinity provider preserves typed Disembark and Battle-shock history. Static owner checks prevent removal and ingress from resetting any turn-history family. |
| Effect duration and circumstances | Removal/serialization preserve timed effects until their actual expiration; `test_phase17d_rule_execution.py` reevaluates the aura against changed presence and geometry. |
| Next-Charge movement lifetime | Both players and all five arrival phases, ordinary and Deep Strike ingress, independent cargo eligibility, reactive/Surge selection, direct mutation rejection and forged history rejection are covered in the Order 64 tests. Shared-owner audits cover Charge, pile-in and consolidation. |
| Exact reconstruction cost and integrity | Canonical facade-driven loaded ingress, Rapid Disembark and a later accepted decision each exercise exact restore and fork independently, with live work-count guards and matched timing evidence. |

The scope/architecture audit confirms that production changes are confined to
reserve policy, shared movement eligibility, historical validation and their
contract boundary. The oversized reserve module delegates destruction policy
and resolution to a focused module. No independent adapter mutation path was
introduced. Focused source, placement, lifetime and replay regressions pass.

Changing the Core descriptor and required serialized history changes deterministic
decision/event history. Existing combat fixtures therefore use reviewed replacement
input identities to exercise their original outcomes; their assertions, RNG and
shared submission/replay paths remain intact. Old forged-payload fixtures now
include the required fields so they continue to reach their intended authority
check instead of failing earlier on schema validation.

Final validation passed 8,467 behavioral tests at 85.12% coverage and all 545
code-quality tests. Lint, formatting, both type checkers, all 11 import contracts,
pre-commit, the regenerated eight-shard inventory, source/build/contract
reproducibility, exact-base compatibility, TypeScript generation/type checks,
five client unit tests, 342 conformance assertions and installed-wheel smoke passed.
All six matched reconstruction comparisons and live work budgets passed. See
[performance evidence](performance/order64/README.md) and the machine-readable
[validation record](performance/order64/validation.json).
No named handler, faction content, permissive restore path or architecture-boundary
change is part of this order. Order 65 Firing Deck and Order 66 Aircraft remain
separate. No production code changed after the successful behavioral coverage
run began.
