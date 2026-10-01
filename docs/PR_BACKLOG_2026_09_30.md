# Approved additional PR backlog — 30 September 2026

The owner approved this backlog during Order 101 / PR #524. Existing Core Rules
order numbers remain unchanged. One implementation PR remains open at a time;
both independent reviews must be clean on the final head, and all required local
and hosted validation must pass before merge. None of the work below is certified
or implemented by this backlog entry.

## Sequence

1. Complete Order 101 / P03F, including its current restore repairs, exact-head
   independent coding/Astra reviews and full validation; verify merged remote main.
   Completed in [PR #524](https://github.com/SobolGaming/Warhammer_40k_AI/pull/524);
   remote main verified at `38ce2265b81f2c0b2c9c668dae7536c239095193` on 1 October 2026.
2. Implement `THROUGHPUT-AFTER-101` as a separate PR before Order 102.
3. Resume Order 102 onward. Reconcile version 963 full source observations and
   consumer mappings before each affected order; schedule any additional repair
   explicitly without silently renumbering the existing roadmap.
4. Resolve all source-intake entries and required repairs before the fresh-main
   25-category `PFINAL` audit. This entry does not authorize certification with gaps.

## Approved review policy for subsequent work

The owner approved this policy on 30 September 2026. Apply it to orders after
Order 101 and to their implementation, independent coding-review and Astra-audit
prompts. Order 101 finishes under its existing acceptance and validation gates.
Prioritize complete playable rules and faction support within authorized scope.

Block on incorrect rules, normal legal-gameplay failures, save/load or replay
failures reproduced from engine-generated valid state, and explicitly required
trust-boundary failures. Every blocking finding must identify its reproduced
entry path, user impact, normal reachability and violated acceptance requirement.
Clearly distinguish reproduced facts from unproven hypotheses.

Queue deeper tamper resistance and coordinated hand-edited-history findings in
a separate integrity-hardening backlog when no normal path or necessary supported
input boundary is demonstrated. A public parser's existence alone does not explain
which expanded guarantee the order requires; identify the supported input and
explicit acceptance requirement. Keep reviews within the order's acceptance
criteria and affected behavior. Expansion requires an explicit decision.

Retain required regressions, positive legal-path controls, truthful source evidence
and exact-head validation. Both complete local and hosted behavioral gates, all
other required checks, and both clean exact-head reviews remain mandatory before
merge. This policy does not itself authorize a merge, new implementation scope,
or certification with unresolved rules/support gaps.

## THROUGHPUT-AFTER-101

Remove measured repeated immutable setup while retaining assertions and fresh
mutable game state. Prior inspection found the Aeldari weapon-profile test
constructs the full catalog three times (reported case time 115 seconds), and its
Harassment Fire test six times (235 seconds). Re-measure on the reviewed base;
reuse the immutable catalog within each test where source ownership permits.
No safely redundant behavioral tests have been established.

Profile the full 45-layout battlefield generator comparison (reported about nine
minutes); preserve its complete comparison. Measure Linux worker timings before
rebalancing: the current eight-shard weights came from an 18-worker Mac invocation,
while hosted shards use four workers. Evaluate 12 shards first. Evaluate 16 only
after runner allowance and the six other initial jobs are accounted for. Do not
invent timing profiles or treat missing/skipped shards as passing.

Keep both complete local and hosted behavioral gates, branch coverage >=85%, both
type checkers, generated/contract/package/quality gates, and serial isolated
performance evidence. The owner's condition to consider replacing the local gate
after measured hosted CI approaches 16 minutes is a future decision criterion,
not authorization to remove that gate now. Record baseline/head invocation wall
times, job/setup/artifact durations, complete JUnit inventories, coverage and
runner use. Adopt changes only with measured benefit and unchanged correctness.

Published Order 101 head `2a5eaa60` provides historical timing evidence: local
covered pytest 771.10 seconds; hosted run
[36726559567](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36726559567)
30m03s, longest behavioral job 27m33s including setup/artifacts. These stages
measure different work. Current Order 101 repairs invalidate that head as final
validation for their code; retain the raw evidence for throughput comparison.

## Version 963 source intake

[GDM's maintained App-data mirror changelog](https://gdmissions.app/11th/rules/changelog)
identifies version 963 dated 30 September 2026: five rule/preset changes, five new
FAQ answers and ten translation-only corrections. Parent research verified the
expanded GDM page and English unchanged for those ten Chinese corrections. This
is maintained-mirror evidence under the repository source policy, not independent
Games Workshop publication or verification of the raw App export.

Before implementing, retain full operative source blocks, version/provider/URL,
observation timestamp, SHA-256 and observation fingerprint; reconcile the pinned
repository baseline and existing source/consumer owners. The following are intake
paraphrases, not newly selected runtime authority or resolved interpretation.

| Intake ID | Source change | Source locator | Consumer work to map |
|---|---|---|---|
| V963-SNAP | Snap Shooting hits cannot be critical hits. | [15.09](https://gdmissions.app/11th/rules/changelog#v-963-rules-c0) | Snap hit classification and every critical-hit trigger. |
| V963-SHOCK | Shock Disembark replaces engagement-retention/enemy-fight instructions with charge ineligibility through turn end. | [18.07](https://gdmissions.app/11th/rules/changelog#v-963-rules-c1) | Source packages, transport charge eligibility, fight queues and the historical Order 62 exception. |
| V963-LAYOUTS | Preset A: Sweeping Engagement to Tipping Point; B: Crucible Of Battle to Dawn Of War; C: Tipping Point to Search and Destroy. | [A](https://gdmissions.app/11th/rules/changelog#v-963-rules-c2), [B](https://gdmissions.app/11th/rules/changelog#v-963-rules-c3), [C](https://gdmissions.app/11th/rules/changelog#v-963-rules-c4) | One data workstream with three separately traced layout/deployment comparisons. |
| V963-OBJECTIVES | A unit may control multiple objectives, and a model's OC may contribute to each objective it is within range of. | [Unit](https://gdmissions.app/11th/rules/changelog#v-963-faq-c0), [Model](https://gdmissions.app/11th/rules/changelog#v-963-faq-c3) | One objective workstream with separate unit-control and per-model contribution cases. |
| V963-EXPIRY | Effects remain active at their stated end boundary. | [Duration](https://gdmissions.app/11th/rules/changelog#v-963-faq-c1) | Expiry and boundary sequencing before the next phase/turn. |
| V963-VISIBILITY | An overhanging model draws outgoing LOS from its in-bounds parts; incoming LOS may target any part. | [Visibility](https://gdmissions.app/11th/rules/changelog#v-963-faq-c2) | Directional LOS and battlefield-edge geometry. |
| V963-ATTACHED | Unit-scoped abilities cover the attached unit; model-scoped abilities remain specific to that model. | [Ability scope](https://gdmissions.app/11th/rules/changelog#v-963-faq-c4) | Shared attached-unit scope and per-model effect consumers. |
| V963-TRANSLATIONS | Ten Chinese wording corrections leave English unchanged. | [Translation list](https://gdmissions.app/11th/rules/changelog#v-963-faq) | Provenance/localization review only unless full source comparison proves semantic drift. |

The source researcher owns acquisition and complete-text comparison; this
implementation checkout owns backlog sequencing and later consumer reconciliation.
Avoid concurrent edits to source packages or the selected observation inventory.
No interpretation is adopted solely from the changelog excerpts.

## Subsequent-order review policy and separate integrity queue

The owner approved the [scoped review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md)
for subsequent orders. Order101 keeps its existing gates. Future implementation,
independent coding-review and parent Astra prompts must use that policy and state
the order's acceptance criteria. Blockers need a reproduced entry path, impact,
normal reachability and violated requirement. Deeper coordinated hand-edited-history
findings without a demonstrated normal path or necessary supported-input boundary
belong in a separately scheduled integrity-hardening queue, with evidence retained.
No new hardening implementation is authorized merely by placing it in that queue.
Complete playable rules and faction support are the priority; existing source,
positive-control, regression and exact-head local/remote delivery gates remain.
The owner's later direction supersedes the Sol High/Ultra plan: explicitly select
GPT-6 Astra Extra High for implementation and separate coding review, beginning
with `THROUGHPUT-AFTER-101`. Preserve the additional fresh parent Astra audit and
its exact-head verdict. Track the next few orders' elapsed time and rework without
claiming an unmeasured speed/quality benefit or independent model capacity.
