# V963-SHOCK — current Shock Disembark source and behavior

The owner selected this narrow prerequisite after PR #525 and before Order 102.
The exact PR base is `ae5005f4eb13378190018718c287abd94fb9320d`, after the
owner-approved tiered performance policy. The original source comparison and
historical archives retain `7f45d87d3094c76beb1be58e0cabb721dec21053`. Existing order
numbers remain unchanged. This work does not certify Core Rules or complete-game
performance. Order 102's unvalidated drafts remain outside this branch.

## Selected authority

The complete Game Datamissions live Core body was observed at
`2026-10-01T12:04:31.127429+00:00` from the already-authorized
`https://game-datamissions.com/11th/rules/core-rules` URL. It has no asserted
App-data version. The separately retained v963 changelog identifies the 18.07
change. The former complete rule is the v931 added record; no separately archived
full v946 export is claimed. Game Datamissions is a non-affiliated maintained
mirror under the existing project source policy, without independent GW
corroboration. All three accepted-domain captures returned HTTP 200 with no
redirects and matched the researcher's bytes.

The retained [source audit](../data/source_audits/v963_shock/source.audit.json),
[full records](../data/source_audits/v963_shock/selected-records.json),
[comparison](../data/source_audits/v963_shock/comparison.json) and
[capture receipts](../data/source_audits/v963_shock/capture-verification.json)
separate canonical JSON hashes from flattened runtime transcription hashes.
`tools/build_core_transports_source.py --check` re-extracts the selected records
from retained literals offline, reproduces current package/audit bytes and checks
the immutable prior package. No provider page is runtime input.

| Obligation | Current disposition |
|---|---|
| 18.07 source permission, embarked passenger, placed Transport, no embark into it this phase | Unchanged existing permission and eligibility owners |
| Wholly within three inches; 03.02 coherent, unengaged setup | Shared grouped disembark geometry; Shock engagement exemption removed |
| Prior passenger engagement retention and mandatory enemy Fight selections | Superseded by current full 18.07; no Shock queue producer or mandatory restore disposition |
| Ineligible to declare charge until end of turn | Existing typed state/query, retained through all turn-end rules, then expired |
| Duration FAQ | Restriction includes its stated boundary; absent before the next part |
| 12.08 Engaging forced enemy Fights | Complete source unchanged; shared queue, completion, restore and replay retained |
| 04.03.05 and weaponless FAQ | Complete source unchanged; selection with no attacks remains Order 102 work |

Emergency, Combat, Assault, oversized placement and source-grant restrictions
keep their separate authority. Other v963 families remain in the approved intake
backlog, including general effect expiry; this change handles only Shock's state.

## Ownership and compatibility

`standard_disembark_resolution` and grouped disembark resolution use
`transport_disembark_geometry` for endpoint legality and shared coherency.
Movement placement atomically commits placement, cargo, state and completion
event. Its Shock-only queue producer is removed. The lifecycle validator keeps
permission, accepted-decision and physical-history checks; it no longer requires
a started/skipped queue event. `shock_disembark_history` verifies unengaged setup.

The existing `can_declare_charge: false` state feeds `charge_eligibility`.
`GameState.clear_turn_action_states` preserves Shock alone through late mission
turn-end rules. `GameState.expire_shock_disembark_after_turn_end` runs after the END_TURN
completion marker and before round-end rules; direct GameState turn advancement
uses the same idempotent expiration. Other state/effect cleanup is unchanged.
The baseline allowed a charge-eligibility query after cleanup during mission
turn-end processing; no actual late charge consumer was reproduced. The narrow
duration correction fulfills the explicit boundary acceptance requirement.

The proposal, decision, event, view and persistence family shapes stay unchanged.
Shock's required start-engagement list and engine-authored post-engagement list
remain empty. Clients still submit pending engine-authored choices and must not
assume a forced response. Shared Engaging contexts remain supported. Atomic
proposal validation/mutation, rejected-proposal handling and the engine-owned
pending-continuation protocol remain unchanged; this source correction changes
legal placements and queue production without breaking that supported client
protocol. Bundle 42.1.0 records the normative current-source change, with unchanged
family/persistence versions. Exact-base compatibility validation is required in
addition to this semantic assessment; equal field shapes alone do not justify it.
Old saves and replays require their original runtime under the existing
compatibility policy. No migration, compatibility shim or rewritten old queue is
provided; released baselines and retention obligations remain intact.

## Historical evidence and current controls

The original Order 97 manifest, selected sources, source capture, categories,
runtime receipts and reviewed-inventory fingerprint remain unchanged. A bounded
[five-file mapping](../data/source_audits/v963_shock/historical-inputs.json)
retains 1,337,933 bytes authenticated against exact base Git objects and all
applicable original byte pins. The historical validator resolves only these
exact paths to hash-checked copies and fails on missing/corrupt copies. It still
checks the original assertions and fixture dependencies; a historical success is
not a current-source compliance claim.

Five obsolete Shock-host test functions (82 assertions) are retired from live
execution and retained in that snapshot. They covered the former forced Fight
producer, skipped disposition, public queue and completed/active queue history.
Two direct checks of the removed Shock-only phase-selection helper are also
retired from the otherwise retained malformed forced-context test; its shared
typed-context checks remain live. These obsolete checks remain in the same
authenticated historical file. Three now-unused local test helpers and the
private lineage checker called solely by the retired Shock history validator
are removed. Shared Engaging authentication still uses its existing owner.
Current regressions cover unengaged setup, engaged rejection, state preservation,
malformed/stale proposal boundaries, both viewers, actual JSON restore, replay
and duration. The existing permission, grouped/oversized placement and adjacent
transport matrices remain active.
The duration regression also uses a real Tactical mission scoring pause after
cleanup: JSON persistence, both viewers/events, restored Retain choice, next-turn
expiration and exact replay. The optional Score branch exposed the same existing
secondary scoring evidence failure on exact base and current runtime. That
separate scoring follow-up is not repaired or claimed fixed by V963-SHOCK.

The unchanged `test_p12_consolidation_forces_each_opponent_once_and_resumes_through_facade`
and `test_p12_full_fight_phase_reconstructs_ordinary_continuation_and_forced_overrun`
retain real Engaging two-enemy Normal/Overrun completion, suspension/resumption,
no double selection, active/completed restore, both viewers, exact replay and
later-round continuation. No shared forced-Fight completion owner is removed.

## Delivery evidence

Focused current-source regressions first reproduced the old queue/setup behavior.
Independent duration probing has passed with the new state lifetime, including
actual JSON persistence, viewer/event equality and exact replay. Delivery also
requires generated, contract, performance, full coverage/quality, exact-head
reviews and remote CI. Their command receipts, actual input hashes and run/head
identities are retained in the task's `v963-shock-state` directory and PR record;
this scope document does not substitute for those passing receipts.
The [exact-base assessment](performance/change-assessment.json) and
[performance policy](performance/PERFORMANCE_POLICY.md) govern current evidence.
The earlier three-sample Shock comparison predates the GameState ownership
repair and remains historical task evidence, not a current passing gate.
The 62 Windows refresh reports and 14 failed inequalities remain preserved in
the separately archived task evidence; their original failures are unchanged.
Policy-pinned historical report bytes remain at their original repository paths.
Current detailed evidence covers the removed unconditional reconstruction event
scan and Shock-specific restore/replay history work: six existing generic
restore/fork cases with seven samples each, plus active and normally expired
Shock restore/replay cases with three samples each. The actual policy-merged
base and current runtime use the same current drivers, fixtures, lock and
declared provisional host. Preparation and correctness assertions are excluded
from component timings; the separate required smoke includes process startup.
The new Shock family's first immutable current comparison establishes its
workload reference; it does not represent a pre-existing historical measurement.
No complete-game or deferred-budget certification is claimed.
Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`; deeper coordinated-history
hardening without a necessary supported boundary remains separate work.
