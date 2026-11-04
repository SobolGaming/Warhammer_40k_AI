# Emperor's Children six-clause read-only audit

Reviewed production head: 21dd70655bdbc96fc8d77944d7302eea62458ba5. At completion the parent advanced the shared checkout to merge e921b927e0de21070df8398c63494510c5461f45; `git diff --stat 21dd70655bdbc96fc8d77944d7302eea62458ba5 e921b927` was empty and `git status --short` was empty. No repository files were changed by this audit. Evidence files are confined to ec-audit.

Applied docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md. This is a scoped source/native-consumer audit, not independent implementation-review signoff, a support-status upgrade, full-game certification, or certification of all persistence/replay paths.

## Current source disposition

The parent captured complete canonical rendered main.innerText for Lord Exultant, Tormentors and Infractors and each Updates page, with UTC timestamp, URL, FNV-1a over UTF-16 code units and UTF-16 length. This child environment had no browser surfaces, so it did not claim a direct independent browser observation. verify_captures.py verifies all six parent capture FNV/length values, saves exact UTF-8 text, and computes SHA-256. See captures.jsonl, capture-receipts.json, clause-comparisons.json and the six ec-*-*.txt files.

All six operative clauses match the retained source semantics. Euphoric Strikes and Excessive Assault are byte-exact. Objective Defiled and both Icon rows differ only in curly versus straight apostrophe. LORD OF THE HOST additionally renders faction/BATTLELINE keywords uppercase. Every retained normalized_text SHA matches its unchanged recorded SHA. None requires replacement operative wording or rewriting an old source observation.

| Row | Clause | Source disposition | Native audit disposition |
| --- | --- | --- | --- |
| 000004078:4 | Euphoric Strikes | Exact | No new defect reproduced; existing native activation/decline, source-model-only melee modifiers, expiration, once ledger, pending restore and replay control passed. |
| 000004078:5 | LORD OF THE HOST | Presentation only | No new defect reproduced; existing attached/unattached Infractors/Tormentors setup grant controls passed. Leading relationship and BATTLELINE gating live in shared conditional-leader owners; actual allowed attachment targets constrain the faction. |
| 000004079:3 | Objective Defiled | Apostrophe only | No new defect reproduced; own Command-end producer and zero/tie/strictly-greater-enemy retention controls passed. |
| 000004079:4 | Icon of Excess | Apostrophe only | Affected by confirmed shared opponent-Fight omission; same descriptor/consumer as reproduced Infractors row. A separate native Tormentors kill was not run. |
| 000004080:3 | Excessive Assault | Exact | Native real melee rerolls observed in both turn-owner variants; source constrains melee and objective upgrade. No additional proven defect. |
| 000004080:4 | Icon of Excess | Apostrophe only | Confirmed opponent-Fight omission through native adapter submissions and attack destruction. |

Current pages show Toughness 5 for all three datasheets; the existing emperors_children_profiles_2026_10.overlay-pack.json already patches rows 000004078:1, 000004079:1, 000004080:1 to T5. Existing Lord native-profile test explicitly asserts T5. This audit did not broaden into a numeric-profile correction.

## Blocking finding EC-ICON-OPPONENT-FIGHT

Requirement violated: the current and retained Icon wording says end of **your Shooting phase or the Fight phase**. The latter includes the opponent's Fight phase. The bearer unit must take its Leadership test after destroying at least one enemy unit in that phase, with 1CP on success subject to the normal cap.

Entry path: the existing tests.support.faction_batch01 source-backed fixture loads seven actual datasheets; native muster creates ten Infractors with one Icon and five Rangers. The existing scene establishes a bounded Fight checkpoint and real placements. Existing fight_to_end drives LocalGameSession finite/proposal submissions, real melee declarations, dice reroll decisions, allocations, damage and unit destruction through phase end. No production method or RNG was replaced, no manual casualty/destruction history was injected. Repro uses seed faction-batch01-ec-fight-2, once with active=owner and once with active=opponent. Initial fixture/setup is constructed and non-strict; this does not prove prior public setup traversal or a full legal roster, but the actual failure follows legal engine-issued combat choices with native destruction evidence.

Observed result:

| Active player in Fight | Native enemy model destructions | Native Excessive Assault reroll decisions | Icon Leadership tests | Icon OTHER CP |
| --- | --- | --- | --- | --- |
| owner | 5 | 8 | 1, roll 9 vs LD6, pass | 1 |
| opponent | 5 | 8 | 0 | 0 |

Impact: the owner loses the required Leadership test and resulting opportunity to gain CP when their Icon unit destroys an enemy during the opponent's Fight phase. This is an ordinary legal combat trigger, not coordinated hand-edited-history hardening.

The raw reproduction field target_alive_models mistakenly reads the immutable initial fixture object; ignore that field. Corrected icon-reproduction-summary.json identifies this limitation explicitly. Five native model_destroyed events per case and final session payloads are retained. The native target completion is not inferred from that stale field.

Root cause/owners:

- tools/generate_emperors_children_infractors_tormentors_rule_ir.py:220-279 emits both Shooting and Fight clauses with owner=active_player (line235).
- Both 000004079:4 and 000004080:4 therefore carry the wrong Fight owner in faction_pack_rule_ir/artifacts/shards/emperors-children.json.
- engine/catalog_command_point_support.py:100 onward admits only owner=active_player for phase CP gains.
- engine/catalog_command_point_runtime.py:500-508 rejects any phase gain when event.active_player_id differs from source.owner_player_id.
- The event_subscriptions filter at line241 is player_id=source.owner_player_id. Preserve this ownership filter: faction_content/events.py:529-537 explicitly distinguishes recipient player_id from active_player_id. Removing the filter would risk cross-owner duplicate candidates; it is not itself the erroneous active-turn predicate.
- catalog_command_point_runtime.py:_source_unit_destroyed_enemy_unit_this_phase uses native phase-completion attribution and shared attached rules-unit identity, which should remain intact.
- catalog_command_point_test_evaluation.py owns Leadership and normal command-point ledger application; preserve those owners and cap behavior.

Smallest complete proposed repair (not implemented): keep the unchanged source text and hashes; generate owner=either_player for both Icon Fight clauses only, retaining owner=active_player for own Shooting. Reuse the existing either_player timing vocabulary (catalog_fight_end_triggered_movement_support.py:104). Extend the shared CP exact descriptor/validation and target eligibility to honor recognized trigger-owner semantics, rejecting unknown/unsupported owners. Preserve owner-recipient subscriptions and ensure one candidate per source/current phase. Rebuild only affected authenticated/generated artifacts and their required manifests/contracts as governed by repository checks. No ability-name or source-row-specific runtime branch is justified.

Bug-class search: inspected shared CP phase source selection, event subscriptions, target eligibility, source destruction attribution and typed descriptor acceptance. Enumerated every timing-window MODIFY_COMMAND_POINTS clause in the faction_pack_rule_ir artifact shards; only the two Icon source records occur (cp-phase-bug-class.json). That enumeration does not claim all catalogs/packages contain no other CP forms. Shared own-phase CP providers outside these shards still require regression controls before changing the generic owner gate; do not silently broaden other source clauses to either-player.

Proposed acceptance:

1. Both Icon native source rows retain exact operative wording and normalization hashes; regenerated Fight IR has validated either-player ownership and Shooting stays own-only.
2. Native owner and opponent Fight destruction each produce exactly one Leadership test per eligible living bearer source, with success/failure/capped CP controls; both datasheets exercised.
3. Own Shooting remains eligible; opponent Shooting stays ineligible. No kill, wrong killing unit, friendly target, absent/dead Icon, stale prior-phase destruction and unrelated unit remain negative controls. Preserve attached-rules-unit attribution.
4. Existing own-phase/during-Command CP source families keep their recipient and active-turn restrictions. Unknown owner values fail closed.
5. From engine-generated valid state, save/restore and exact replay preserve pending decisions or subsequent phase-end consequences on the newly corrected opponent-Fight route. Do not rely solely on descriptor/load tests.
6. Preserve all required exact-head source integrity, regression, generated, coverage, local/hosted CI, independent coding review and fresh parent Astra audit gates. This audit does not satisfy those final implementation gates.

## Supporting checks and paths

Existing focused checks: 15 passed, 40 deselected in 76.65s. Command was pytest tests/factions/emperors_children/test_selected_consumers.py tests/rules/section14/test_secured.py with -k 'native_leader_attachment_controls or euphoric_strikes_native or icon_does_not_gain or secured_zero_tie or native_tormentors_source', --no-cov, no cacheprovider and evidence-folder basetemp/JUnit. Results focused.log and focused.xml. These are bounded controls, not a full suite.

Other traced shared owners: catalog_once_per_battle_runtime.py (Euphoric choice/usage); catalog_datasheet_rule_descriptors.py:255 conditional leader grants and :1099 passive objective rerolls; catalog_conditional_leader_queries.py for physical source/leader/bodyguard gates; catalog_sticky_objective_support.py and catalog_sticky_objective_runtime.py for Objective Defiled; catalog_datasheet_rule_runtime.py:877 and attack_sequence_dice_rerolls.py:1213-1310 for melee Wound rerolls/target objective range. Existing tests distinguish model-local Euphoric effects from bodyguard/ranged profiles and verify actual setup grants on the leading model.

One exploratory Excessive Assault off-objective probe was attempted in repro_excessive.py but stopped before combat at its assertion that the chosen target location was outside objective range. No behavior finding or passing test is claimed from that failed fixture, and its scratch/log are preserved. Optional versus imperative reroll wording was not elevated to a blocker without a completed source-qualified reproduction.

## Evidence hashes

- capture-receipts.json SHA256 38d9fc2d0126246974fd9814abad429b10d28d3d7ceafe7c6a1544a8d999354e
- clause-comparisons.json SHA256 7d248c5923cc27b8f571f265b360f2ddf84c0dcc5138768abea5179c00f11377
- icon-reproduction-summary.json SHA256 db246206417b3a1c51d31d4476824f192a3d66dca963f923851dfa905a9bff2d
- icon-opponent-fight-reproduction.json SHA256 a4325baf4d0cb624b06c34e1de12c1f772a512385c84f90aba17d4f22343cc1c
- icon-owner-session.json SHA256 3c46a4bf192ba49713fd193b02e21a397104c95e6e59920d6c226cfd4806118c
- icon-opponent-session.json SHA256 31a04d9c3d93937466c3cf90d17fe09bcbaa18a6c410a05702764ee2951337e0
- focused.log SHA256 55fc8f56d02383fb5dfae63ffc9cf3499e4e46c618a985152a3a62ac55129f86
- focused.xml SHA256 9adf5b7e7912f50373173789591f89e06acded6c0dbdc0ed04323020f58fde5f

Current text UTF-8 SHA256: Lord 818037f2d6c51d49d3fa9c1f999ef3b93371376dd50bf1c92cbd1d2bf1819965; Tormentors 4e6cea797bd4658feeb99de5fa13a548cdc7a22f51df04d0924e7336c48a3fcb; Infractors 122e59d55f54e60c3cfbcf2fd2a6ad635407f0c66d6d07cb274b90818017905d. History SHA256/URLs/UTC/FNV/length are in capture-receipts.json.

Remaining blocker: the proven Icon opponent-Fight defect. No implementation was authorized for this subtask and none was performed. There is no pending approval denial or uncertain mutation outcome.
