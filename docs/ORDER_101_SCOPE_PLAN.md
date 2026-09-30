# Order 101 / P03F — failed move-type setup selection

C03-06 left a unit selected to move after a complete setup failed. The only
pending choice was another placement submission, so an impossible setup trapped
the phase. Order 97 reproduced this with a 100-inch circular cargo base on the
60 by 44-inch battlefield.

## Source and obligations

The complete selected Game Datamissions observation is already retained in
`data/source_audits/order97/selected-sources.json`. It is the unversioned body
observed for Orders 84 and 97, under the maintained App-mirror source policy.
No new source observation, provider, or runtime source package is claimed.

| Clause | Obligation |
|---|---|
| 03.02-obligation-04 | A failed complete setup leaves the entire unit at its prior location. |
| 03.02.01-obligation-01 | A unit returned after failed move-type setup has not been selected to move. |
| 03.02.01-obligation-02 | It may be selected later, attempt another setup, or Remain Stationary. |

The selected `03.02.01` row is `rule:03:03.02.01:1`, fingerprint
`28bc62101a93e202a54e55347fd55736350d1afd0fb33eec725ee818b01d48e8`.
The shared engine rollback receipt references that immutable audit observation.
The retained negative probe and its JSON remain historical discovery evidence.

## Shared authority and bounded scope

The existing placement validation never commits a partial invalid placement.
After a well-formed rule-invalid ordinary move-type setup, the shared placement
owner cancels only the unresolved active movement selection. Battlefield poses,
cargo, reserves, completed selections and movement-distance records remain
unchanged. Disembark modes and reserve Ingress use the same rollback.

The pending request becomes the existing `select_movement_unit` authority. The
player can select another legal unit or reselect the failed one and use the
ordinary `select_movement_action` options, including legal Remain Stationary or
another setup. Every attempt receives fresh selection, action and proposal IDs.
Malformed, stale and context-drift submissions retain their existing pre-record
atomic rejection, with no cancelled selection. The separate Combat Disembark
diagnostic that Tactical placement is available does not establish failed setup;
it retains the existing Tactical/Combat proposal retry.

This search also covered deployment, destroyed-Transport emergency placement,
Stratagem/reaction ingress, revival, and return-to-battlefield consumers. They do
not consume an ordinary Movement-phase selection through this placement owner,
so this order does not give them ordinary movement eligibility or undo their
mandatory continuations.

`movement_setup_failed` binds the invalid-placement event and both recorded
selection/proposal decisions to before/after movement authority. Restore checks
the source pin, decision identities, rollback and later explicit reselection.
Shared adapter redaction removes internal movement snapshots from public events.
Restore derives the complete selected/completed/active selection projection from
ordered selection and activation-ending events, including their witness-derived
distance records. A receipt cannot erase another completed activation or reuse
superseded selection, action or rejection authority. Each linked decision needs
its exact request and recorded event, correct actor and phase context, and causal
order. Tactical setup, mandatory destroyed-Transport placement, and reactive
ingress retain their own completion classification.
Rejected attempts retain the same engine source authority as successful setup.
Reserve failures share request/context, diagnostic and source-chain validation
with arrivals, and bind carried ReserveState to the lifecycle owner's authenticated
historical entry inventory. Disembark closes its distinct initial and retained
Tactical-available retry schemas, physical army/model lineage, typed diagnostic,
and causal predecessor order. Canonical outer decisions must match their nested
proposals. Snapshot restore authenticates historical source events; replay
re-execution additionally recomputes physical request context.

Existing decision and proposal shapes remain in use; the adapter contract records
the changed continuation and the new audit event. Runtime identity and external
contract examples must be regenerated.

## Validation evidence and remaining merge gates

The current repaired source candidate is
`warhammer40k-core-v2:runtime-tree-sha256-v1:9e98b1adc7c63d919a1659ab93becf6a1e956e401d0948a464d004f89137376f`.
Its independent pre-freeze retry review found no remaining concrete defect in the
affected owner. Current isolated measurements completed all 21 Order101 samples in 43.002
seconds and all 27 inherited workloads with verified report/log hashes and
unchanged numeric budgets. A progress-file write failed after nine saved
workloads; those were verified and reused, and only the incomplete row10 receipt
was repeated before completing the remainder. Successful child-command wall times
sum to 364.314 seconds; this sum is not an overlapping workflow duration.
Complete local covered behavior and quality, actual eight-shard hosted CI, and
both clean reviews on the final published commit remain required.

Fresh Astra review of the prior published head `e9e7d150` found a normally
reachable save/load failure: ordinary failed Disembark, select another unit,
Advance, submit a rejected 100-inch path, submit a valid retry, Embark, then load
the untouched engine-generated snapshot. Restore rejected the movement proposal
authority even though exact replay succeeded. The same shared defect existed on
base without the failed-setup prefix. The completion validator counted rejected
and accepted proposals sharing one action instead of resolving the accepted one.

The bounded repair changes only the existing movement decision authority and its
Order101 test. Normal Move and Advance bind their explicit terminal proposal ID.
Fall Back retains its existing completion payload, resolving the same-action
proposal after excluding exact owner-produced invalid request/result pairs with
typed diagnostic and canonical request/record closure. Existing action, actor,
source, witness and physical checks remain; rejected records are retained. No
schema, generic retry framework or historical geometry recomputation is added.

Six permanent legal facade cases passed exact restore, replay and both viewer
projections: repeated Normal/Advance rejections with and without failed setup,
and one/two genuine Fall Back rejections before a six-inch retreat and Embark.
The independent reviewer separately passed all three move kinds with two real
rejections each and nine labeled owner-level rejection negatives. These focused
results and the pre-freeze verdict do not replace final exact-head validation.

The earlier runtime `bc6eb667`, published at `e9e7d150`, passed 10,201 covered
behavioral cases with zero failures/errors/skips and aggregate coverage with
branches enabled 85.199%; command wall time was 782.742 seconds. Its complete
quality suite passed 797 cases in 112.484 seconds. Hosted run
[36773388347](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36773388347)
passed all sixteen jobs, eight actual behavioral shards and coverage in 29m08s.
Those successes and its earlier clean coding report are archived old-head
evidence. Astra's demonstrated normal restore defect superseded approval; the
production repair invalidates their applicability to the new source.

The terminal cargo bridge follows existing authenticated mutations from the
reconstructed failed-setup boundary through later Embark/Disembark, casualty and
receiving-unit revival. It checks the affected physical components against their
terminal carrier. A real later nonzero passenger transfer exposed an existing
restore error: the delayed movement completion was applied after Embark departure.
Shared movement decision authority now binds that report to its accepted
pre-Embark move; both model history and Primary physical history use that binding.
Normal Move, Advance and Fall Back retain their distinct existing authority.

The genuine failed setup/retry followed by a 4.5-inch move and another carrier
Embark now restores and replays exactly, including both viewer projections.
The affected four-case batch passed. Three emergency controls use actual single,
attached-group and nonempty whole-Leader omission owner events to exercise the
suffix directly; they do not claim full combined failed-prefix snapshot/replay
coverage. The prior full focused iteration had 95 passes and this one transfer
failure; its changed target was rerun successfully after the complete owner fix.
The final full covered suite is still mandatory.

The prior runtime's full Ruff/format, mypy, pyright, import boundaries, pre-commit, unchanged eight-shard
inventory, generated identity, Order97 receipts/inventory, base-ref contract
compatibility, TypeScript checks/unit/conformance and installed-wheel gates passed
before the new retry repair. Its isolated Order101 measurement completed 21 samples in
41.96 seconds and its unchanged budget gate passed. All 27 inherited measurement
commands completed in 356.14 seconds with exact report/log hashes verified; their
combined numeric assertions remain part of final quality. Complete local covered
behavior and quality, full hosted CI and both exact final-head reviews must be
revalidated on the repaired source.

The previous repair candidate was
`warhammer40k-core-v2:runtime-tree-sha256-v1:237906fd3b3b8a8251baf68e7081f70fe9a7560eb77a93535f3b999b68c3ddfc`.
Its preliminary clean verdict was superseded by R101-CR-006: restore accepted
a snapshot whose four terminal cargo fields were manually changed from a real
carrier B to a real carrier A while complete engine-generated history remained B.
No fully legal, unedited engine-only path to that contradiction was demonstrated.
Order 101 retains its existing historical-integrity gates while this location
bridge is repaired. The completed runtime237 measurements remain archived.
Earlier PR #524 head `2a5eaa60` has no clean final review approval. Its earlier
local/hosted results do not validate subsequent repairs. Fresh final measurements
and local/hosted gates remain required before merge.

The earlier independent whole-invariant pre-freeze review accepted eight genuine histories
exactly and rejected fourteen coherent forgeries on unchanged source/resource
hashes. Controls include complete older Reserve setup, genuine later embarked and
reserve Leader revival, prior Reserve failure followed by failed Rapid Disembark,
automatic attack records between failures, both attached components and two real
friendly carriers. Negatives cover omitted living models/components, nonexistent
or unrelated historical carriers, diagnostic producer drift and missing/late/
non-prefix/config-drifted origins. These focused controls do not replace full
validation or final-commit coding/Astra reviews.

Every failed ordinary setup now shares complete historical inventory authority
and independently reconstructs its exact recorded prefix from the existing
pre-decision lifecycle origin. The generic historical ownership service retains
models pruned by catalog replacement. The failed Reserve consumer supplies exact
living coverage at its original request; accepted-arrival defaults are preserved.
Actual diagnostic producer fields, initial cargo and prior reserve location are
rederived through the shared engine. Strict typed envelopes, Combat
Tactical-available retries and their causal source chains remain distinct.

The Realm retry fixture now uses the real facade and a captured initial payload;
its rejected attempt preserves location, offers fresh selection and replays
exactly. Fourteen retry/tamper cases pass. Its old direct-handler fixture lacked
the independently captured lifecycle origin and was repaired without a restore
fallback. The earlier fixture checks remain historical evidence; current-source cheap
gates are listed above, and complete final validation remains pending.

Serial isolated runtime-bound measurements retain all historical baselines,
workloads and numeric budgets. They must finish before the complete covered local
behavioral invocation. That single invocation supplies successful JUnit and worker
timings; no second no-coverage behavioral gate is allowed. Existing committed
shard-profile metadata is retained as a truthful historical observation of its
recorded runtime/case inventory, never relabeled as this candidate's measurements.
The behavioral filename inventory is unchanged by the review repairs.

The prior published runtime `00e0dca2` had 10,160 passing cases in 771.10 seconds.
Its saved unchanged branch-coverage database recovered at 85.1927209112% after a
reporter I/O failure, without rerunning tests. All old raw receipts, source hashes,
JUnit and worker evidence remain archived. Hosted run
[36726559567](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36726559567)
passed all sixteen checks, including eight actual behavioral shards and coverage,
in 30m03s. These historical results inform throughput work and do not approve the
new runtime. Local pytest and hosted workflow durations measure different stages.

Final required local quality, complete covered behavior, both full type checkers,
generated/contract/client/package/import/pre-commit gates, all actual hosted
behavior shards and combined branch coverage >=85% remain mandatory. Fresh
independent coding and parent Astra reviews must be clean on the exact final
published head. Missing/skipped/stale checks and preliminary source review cannot
approve a merge. The [approved additional backlog](PR_BACKLOG_2026_09_30.md) places
a separate throughput PR after Order 101 before Order 102 and tracks version 963
source intake without renumbering existing orders. Core categories 01–25,
factions and complete-game performance remain uncertified.
