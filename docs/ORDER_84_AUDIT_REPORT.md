# Order 84 complete category survey — outstanding gaps

Generated with `python -m tools.core_rules_order84_audit`; do not edit by hand.

Reviewed runtime: `557803404b549023b2d0271b52a2c8d19f5b994b` (PR #503).
**Core Rules are not certified.**
The survey continued through all 25 categories and all 59 FAQs after finding defects.
It retains 286 rule/update rows and 1,424 rendered source blocks, including examples,
supplemental Stratagem bodies, tables and callouts. These are inventory counts, not
counts of independent rules or proven gameplay behaviors.

The [audit JSON](../data/source_audits/order84/audit.json) maps every observed
row to category owners, regression files and explicit open clause-certification
status. Family regressions do not prove every individual operative clause. Exact retained
source equivalence and clause-specific facade/replay/visibility proof remain open.
The [audit notes](ORDER_84_AUDIT_NOTES.md) describe reproduction, scope and validation.

## Selected candidate observation

Provider: [Game Datamissions](https://game-datamissions.com/11th/rules/core-rules).
This is a non-affiliated maintained mirror.
Observed: `2026-09-24T18:41:22.161671+00:00`. App-data version: **not exposed**.
Public asset SHA-256: `6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`.
Source inventory SHA-256: `9405274f48551a2431857c94d9004b779877f89345dc88955c9b72a74dd72921`.

40k.app category 15 inspected in normal browser; 15.11 complete there and truncated in GDM. No co-versioned full-corpus comparison or official-App observation available; changelog v946 is not a version assertion about this live body.
This candidate is incomplete for certification (C15-10). The retained metadata and
block fingerprints are not a runtime source package or a complete verbatim archive.
The two distinct 09.07.01 entries and untitled 24.37.01 remain separate inventory rows.

## Findings requiring scoped follow-ups

### C01-07 / P01G — Dice result semantics

Evidence class: `capability_gap`. Set-to 7 is rejected by the D6-only override record. No tied-highest/lowest physical-die selection owner was found in dice, override or decision dispatch paths.

Required closure: Add source-backed generic result override and tied-die decisions, preserving physical dice identity, critical/trigger semantics, reroll order, active-player choice and exact replay. Audit descriptors and every dice consumer; do not clamp to six.

Source rows: `rule:01:01.05.07:1`, `rule:01:01.05.08:1`.

### C01-08 / P01H — Overhang and deemed base contact

Evidence class: `consumer_trace_gap`. Fight base-contact predicates test geometric base distance only. No turn-scoped pair authority for the three overhang conditions was found; model/body proximity alone is not sufficient evidence.

Required closure: Represent source-authorized deemed base contact and its actual move witness, remaining conditions and turn expiry in the shared geometry owner. Cover Charge, pile-in, consolidation, target/range consumers and restore. First supply a real overhanging-model facade counterexample.

Source rows: `rule:01:01.04.04:1`.

### C01-09 / P01I — Table-quarter divider geometry

Evidence class: `reproduced_defect`. Primary and secondary quarter consumers independently split at zero-width centre lines. A base edge 0.01 inches from centre is counted inside a quarter although it lies inside the 0.5 mm half-divider.

Required closure: Share the 1 mm divider geometry across primary/secondary occupancy, preserve whole-rules-unit scope, border cases, authenticated score witnesses and replay.

Source rows: `rule:01:01.04.05:1`.

### C02-06 / P02F — Random profile characteristics

Evidence class: `capability_gap`. ModelProfileDefinition and CharacteristicValue carry numeric/sentinel values, not a random characteristic descriptor. DiceRollManager random-M tests bypass the catalog and selected-to-move consumer. Random movement bonuses are a distinct implemented surface.

Required closure: Add source-backed typed random profile values and required once-per-unit M versus per-model/per-weapon evaluation timing. Cover actual catalog loading, selection, dice decisions, repeated uses, restores and replay; retain existing random A/D semantics.

Source rows: `rule:02:02.02.03:1`, `rule:03:03.01.03:1`.

### C02-07 / P02G — Weapons without Strength

Evidence class: `reproduced_defect`. A WeaponProfile accepts source-dash Strength, but the attack consumer passes its zero sentinel to the positive-integer wound table and raises. This is a profile-to-consumer counterexample, not a complete attack replay.

Required closure: Use one structured interaction query that resolves absent Strength as one, without making source dash modifiable. Cover wound resolution and other Strength comparisons through real attack hosts and replay.

Source rows: `rule:02:02.04.01:1`.

### C02-08 / P02H — Ordinary healing selection and exclusions

Evidence class: `reproduced_defect`. The shared healing owner rejects multiple wounded models unless attached and offers a destroyed CHARACTER for ordinary unit healing. Its default chooser is the opposing player unless a producer overrides it; audit source-specific actor authority rather than assume every caller is correct.

Required closure: Separate ordinary unit healing from explicit model revival, exclude CHARACTER only where required, support any unit with multiple wounded models and source-correct chooser authority. Preserve model-specific excess-wound loss; cover attached/mixed units, all producers, facade choices and replay.

Source rows: `rule:02:02.02.04:1`.

### C01-10 / P01J — Off-battlefield revival

Evidence class: `reproduced_defect`. Embarked revival writes one wound even when the source requests full health. The shared non-cargo revival path always requests battlefield placement; non-embarked Strategic Reserve revival remains a consumer-trace gap requiring a legal producer regression.

Required closure: Preserve source-defined wounds and equipment for embarked and reserve returns, transport capacity/destruction exceptions, non-spatial off-battlefield state and later ingress. Retain the Order 82/83 battlefield engagement and anchor invariants.

Source rows: `rule:01:01.02.03:1`, `rule:01:01.02.04:1`.

### C04-04 / P04C — Selection when no attacks can be made

Evidence class: `reproduced_defect`. Ordinary Shooting selection requires a legal weapon/target declaration and can skip the entire phase when none exists. This conflicts with the no-weapons FAQ and Shoot-step eligibility. Fight and retained shooting already have explicit no-attack completion paths.

Required closure: Permit legal unit/type selection without attacks, complete the selected type and apply its restrictions without falsely recording that attacks were made. Cover no weapons, no target, selected-unit hooks, all shared hosts, both viewers and exact replay.

Source rows: `rule:04:04.01.01:1`, `rule:04:04.03.04:1`, `rule:10:10.02:1`, `rule:10:10.04:1`, `faq:9bfa47ed-be8d-4e11-80de-f3832d507ca1`.

### C04-05 / P04D — Random melee attacks split between targets

Evidence class: `explicitly_unsupported`. The shared melee validator explicitly returns random_melee_split_unsupported. An existing regression asserts that unsupported status, so its passing result is not rules compliance.

Required closure: Resolve source-backed attack-generation/allocation timing and expose recorded player allocation for random melee attacks. Preserve total counts, weapon instances, Extra Attacks, Cleave, target replacement, invalid retries and replay; do not invent dice results or timing.

Source rows: `rule:02:02.02.03:1`, `rule:04:04.03.02:1`.

### C02-09 / P02I — General ignore-modifier permissions

Evidence class: `capability_gap`. Generic ModifierIgnoreKind covers M, Advance and Charge. Psychic separately covers BS/WS and hit modifiers. The unrestricted Core permission covering unit rolls and profile/weapon characteristics has no complete shared consumer path.

Required closure: Extend only the source-required generic permission and typed subset decisions to applicable characteristic/roll owners. Keep beneficial and detrimental modifier identities independently selectable, source restrictions, drift rejection and replay. Do not add faction-specific escape hatches.

Source rows: `rule:01:01.05.04:1`, `rule:02:02.02.02:1`.

### C15-10 / P15J — Complete selected source observation

Evidence class: `source_evidence_gap`. The fresh GDM page and rendered UI omit Heroic Intervention mode labels, the +1 CP option and part of its charge sentence. 40k.app displays them. Both observations are unversioned, so a same-version disagreement is not established.

Required closure: Retain a complete selected observation and reconcile it with existing complete Heroic source evidence; compare version identities honestly. Resolve missing text before certification, without overwriting historical packages or unioning contradictory versions.

Source rows: `rule:15:15.11:1`.

## All-category dispositions

| Category | Survey assessment | Regression families |
|---|---|---|
| 01 Core Concepts | Reviewed ownership, membership, retained presence, sequencing, distances, dice and morale. Open dice, overhang, quarter and off-battlefield revival findings; no claim that source loading proves these clauses. | [test_unit_splitting](../tests/unit/test_unit_splitting.py), [test_order36_sequencing](../tests/unit/test_order36_sequencing.py), [test_order82_revival_engagement](../tests/unit/test_order82_revival_engagement.py), [test_phase10j_dice_semantics](../tests/unit/test_phase10j_dice_semantics.py), [test_phase14h_healing](../tests/unit/test_phase14h_healing.py) |
| 02 Datasheets | Reviewed ordered modifiers, terminal values, keywords, profiles and healing. Primitive random-roll tests do not establish catalog-to-lifecycle random characteristics. General modifier ignoring remains narrower than Core. | [test_phase10j1_numeric_rules](../tests/unit/test_phase10j1_numeric_rules.py), [test_phase14h_healing](../tests/unit/test_phase14h_healing.py), [test_phase9c_mustering](../tests/unit/test_phase9c_mustering.py) |
| 03 Moving | Reviewed path versus setup distinction, coherency, model order, zero-distance moves, terrain, maximum-approach proofs and prevalidation. Orders 73–76 fix documented cases; finite solver cases are not a universal completeness proof. | [test_phase10l_unit_coherency](../tests/unit/test_phase10l_unit_coherency.py), [test_phase10i_terrain_movement](../tests/unit/test_phase10i_terrain_movement.py), [test_order54_setup](../tests/unit/test_order54_setup.py), [test_physical_proposal_prevalidation](../tests/unit/test_physical_proposal_prevalidation.py) |
| 04 Making Attacks | Reviewed weapon instances, targeting, replacement, grouping, completion and split allocations. Zero-attack Shooting and random melee splitting remain open. Fight has an explicit no-melee completion path. | [test_target_replacement](../tests/unit/test_target_replacement.py), [test_critical_hits](../tests/unit/test_critical_hits.py), [test_phase15d_fight_resolution](../tests/unit/test_phase15d_fight_resolution.py) |
| 05 Attack Sequence | Reviewed hits, wounds, allocation groups, saves, damage and retained destruction. Existing failed-save replacement and destroyed-referent regressions are evidence; no-strength and dice-override gaps cross this category. | [test_phase13b_shooting_declarations](../tests/unit/test_phase13b_shooting_declarations.py), [test_order58_failed_save_damage_timing](../tests/unit/test_order58_failed_save_damage_timing.py), [test_order57_destroyed_referent_measurement](../tests/unit/test_order57_destroyed_referent_measurement.py) |
| 06 Other Concepts | Reviewed corridor visibility, mortal-wound priority and decisions, hazardous sequencing and FNP. Both mixed-keyword Hazard FAQs route to the shared unit damage service; no new defect identified in this survey. | [test_phase13a_visibility_cover](../tests/unit/test_phase13a_visibility_cover.py), [test_visibility_pathing](../tests/unit/test_visibility_pathing.py) |
| 07 The Battle Round | Revisited REVALIDATE category: phase order, turn owner, start/end timing and actual phase occurrence. No new defect identified; the absence of a standalone remediation row is not certification. | [test_phase9b_lifecycle](../tests/unit/test_phase9b_lifecycle.py), [test_order36_timing_authority](../tests/unit/test_order36_timing_authority.py) |
| 08 Command Phase | Reviewed start sequencing before CP, gain caps, persistent shock, half-strength threshold, embarked/reserve candidates and test deduplication. Historical partial Command package status must be interpreted with the later off-battlefield overlay. | [test_phase11c_command_phase](../tests/unit/test_phase11c_command_phase.py) |
| 09 Movement Phase | Reviewed mixed-presence selection, Advance, Fall Back, Desperate Escape, stationary and Normal Move occurrences. Duplicate 09.07.01 source labels are preserved separately. Intrinsic random M remains open under category 02. | [test_order80_normal_move](../tests/unit/test_order80_normal_move.py), [test_phase10m_movement_actions](../tests/unit/test_phase10m_movement_actions.py), [test_phase10o_fall_back](../tests/unit/test_phase10o_fall_back.py) |
| 10 Shooting Phase | Reviewed Normal/Assault/Close-quarters/Indirect eligibility, penalties, range/visibility and post-shoot Action lifetime. Reproduced selection omission when no attack is possible; this must not be hidden by a passing attack-resolution suite. | [test_phase13b_shooting_phase_declarations](../tests/unit/test_phase13b_shooting_phase_declarations.py), [test_phase13b_shooting_declarations](../tests/unit/test_phase13b_shooting_declarations.py), [test_order65_firing_deck](../tests/unit/test_order65_firing_deck.py) |
| 11 Charge Phase | Reviewed modified range, replacement targets, all-model endpoints, engaged-model restrictions, flight declaration timing and complete dice rerolls. Existing Order 47 and 74 cases retained; deemed base contact remains open. | [test_charge_distance_continuation](../tests/unit/test_charge_distance_continuation.py), [test_charge_rerolls](../tests/unit/test_charge_rerolls.py) |
| 12 Fight Phase | Reviewed mandatory activations/pass, Fights First, Overrun, pile-in and three consolidation modes. Owner v946 resolution in Order 72 governs Engaging-only responses; do not revive superseded Ongoing erratum. Random attack splitting remains unsupported. | [test_phase15c_fight_order](../tests/unit/test_phase15c_fight_order.py), [test_phase15d_fight_resolution](../tests/unit/test_phase15d_fight_resolution.py) |
| 13 Terrain | Revisited terrain revalidation: terrain areas versus features, cover, detection, Hidden and causal concealment. Order 78 covers Gone to Ground outside dense terrain; preserve exact solver unresolved results as errors, never visibility answers. | [test_order78_gone_to_ground](../tests/unit/test_order78_gone_to_ground.py), [test_phase10i_terrain_movement](../tests/unit/test_phase10i_terrain_movement.py), [test_phase13a_visibility_cover](../tests/unit/test_phase13a_visibility_cover.py) |
| 14 Objectives | Reviewed marker/terrain geometry, control sums, tied control, securing and phase/turn-end precedence. Order 79 protects control before cleanup; Aircraft dash OC is not a numeric control counterexample. | [test_order79_control_first](../tests/unit/test_order79_control_first.py), [test_phase11b_objective_control](../tests/unit/test_phase11b_objective_control.py) |
| 15 Stratagems | Reviewed all ten Core Stratagems plus Snap, limits, affected units and final CP bounds. Fresh GDM 15.11 display is truncated; 40k.app exposes both modes and +1 CP. These unversioned observations cannot establish same-version equivalence. | [test_command_reroll_costs](../tests/unit/test_command_reroll_costs.py), [test_heroic_intervention](../tests/unit/test_heroic_intervention.py), [test_phase12c_core_stratagems](../tests/unit/test_phase12c_core_stratagems.py) |
| 16 Actions | Reviewed eligibility, no-shoot/no-charge duration, Battle-shock, completed-move interruption, departures and exceptions. Order 77 repairs return-to-start paths. Complete family/viewer/replay coverage still needs clause-level sign-off. | [test_phase11e_mission_scoring_cleanup](../tests/unit/test_phase11e_mission_scoring_cleanup.py), [test_action_movement_interruption](../tests/unit/test_action_movement_interruption.py) |
| 17 Monsters And Vehicles | Reviewed Normal/Advance friendly transit and engaged shooting target/model scopes. Order 71 tests both penalty causes and close-quarters target exception; no additional defect identified. | [test_order53_movement_abilities](../tests/unit/test_order53_movement_abilities.py), [test_phase13b_shooting_declarations](../tests/unit/test_phase13b_shooting_declarations.py) |
| 18 Transports | Reviewed capacity, setup-turn embargo, all disembark modes, ingress restrictions, hazard-before-placement and maximal emergency placement. C18-07 uses owner resolution; do not inherit Transport engagements. Embarked full-health revival is a new cross-category failure. | [test_order55_disembark](../tests/unit/test_order55_disembark.py), [test_order60_emergency_disembark](../tests/unit/test_order60_emergency_disembark.py), [test_order61_embark](../tests/unit/test_order61_embark.py), [test_order63_reserve_transports](../tests/unit/test_order63_reserve_transports.py) |
| 19 Attached Units | Reviewed canonical identity, component lineage, starting strength, abilities, keywords, destruction and revival. Healing candidate exclusion is model-keyword scoped and must survive attachments. | [test_phase15c_fight_order](../tests/unit/test_phase15c_fight_order.py), [test_order82_revival_engagement](../tests/unit/test_order82_revival_engagement.py), [test_unit_splitting](../tests/unit/test_unit_splitting.py) |
| 20 Strategic Reserves | Reviewed setup limits, cargo accounting, first-round gate, end-round-three/final-turn cleanup, repositioning effects and restrictions through next Charge. Revival of a non-embarked reserve unit has no distinct unplaced path in shared healing; retained as a consumer-trace gap. | [test_order64_reserve_lifetimes](../tests/unit/test_order64_reserve_lifetimes.py), [test_order63_reserve_transports](../tests/unit/test_order63_reserve_transports.py), [test_phase16c_reserve_declarations](../tests/unit/test_phase16c_reserve_declarations.py) |
| 21 Flying and Surging | Reviewed Take to the Skies timing and movement cost, Hover, Surge trigger/Battle-shock/engagement/history, fixed-target approach and Aircraft exclusions. Flight/Heavy vertical-distance regression explicitly retained. | [test_order51_flight](../tests/unit/test_order51_flight.py), [test_order52_surge](../tests/unit/test_order52_surge.py) |
| 22 Other Rules And Abilities | Reviewed self-Aura and duplicate identity, faction ownership gate, leveled Psychic per-phase use, wargear bearer loss and Plunging Fire. Psychic use key already includes active player, round and phase; not the old Normal Move bug. | [test_phase17d_rule_execution](../tests/unit/test_phase17d_rule_execution.py), [test_phase13b_shooting_declarations](../tests/unit/test_phase13b_shooting_declarations.py) |
| 23 Aircraft | Reviewed mandatory reserves, ingress-only movement, opponent turn-end removal, transit and targeting/melee/flying restrictions. Hover preserves AIRCRAFT identity. No new defect identified in this survey. | [test_phase10r_aircraft](../tests/unit/test_phase10r_aircraft.py) |
| 24 Core Abilities | Reviewed all 39 headings and subclauses: duplicate source/choice, conditional keywords, attack timing, every-model gates, Firing Deck, Heavy, per-instance One Shot, Psychic subsets, Scouts, Super-heavy Walker and Torrent incompatibilities. Weapon instance ownership already exists; no blanket missing-One-Shot claim. | [test_wargear_weapon_profiles](../tests/unit/test_wargear_weapon_profiles.py), [test_lethal_hits](../tests/unit/test_lethal_hits.py), [test_order65_firing_deck](../tests/unit/test_order65_firing_deck.py), [test_order51_flight](../tests/unit/test_order51_flight.py), [test_phase13b_shooting_declarations](../tests/unit/test_phase13b_shooting_declarations.py) |
| 25 Muster Armies | Reviewed 1000/2000 limits, single 3DP Incursion exception, duplicate counts, faction/detachment restrictions, Support attachment, model Warlord/bearer and Upgrade exceptions. Orders 67–69 retained; no faction catalog certification inferred. | [test_phase9c_mustering](../tests/unit/test_phase9c_mustering.py) |

## Prior obligations and cross-category checks

All 18 distinct v931 obligations and the v946 obligation are retained below.
These are rechecked implementation links, not new final-certification claims.

| Obligation | Existing owner finding | Category |
|---|---|---|
| v931-splitting | C01-02 | 01 |
| v931-assault | C18-04 | 18 |
| v931-shock | C18-05 | 18 |
| v931-psychic | C22-02 | 22 |
| v931-deadly-demise | C24-06 | 24 |
| v931-ongoing-erratum | C12-03 | 12 |
| v931-insane-bravery | C15-06 | 15 |
| v931-embarked-abilities | C01-03 | 01 |
| v931-retained-presence | C05-02 | 05 |
| v931-charge-replacement | C11-03 | 11 |
| v931-objective-terminology | C14-02 | 14 |
| v931-scout-alternation | C24-07 | 24 |
| v931-critical-success | C04-02 | 04 |
| v931-snap-critical | C04-03 | 04 |
| v931-damage-zero | C05-04 | 05 |
| v931-keyword-loss | C02-04 | 02 |
| v931-any-part-visibility | C06-01 | 06 |
| v931-flight-timing | C21-01 | 21 |
| v946-rapid-disembark | C18-06 | 18 |

The split erratum duplicates the Splitting Units obligation. The v931 Ongoing erratum
is historical: C12-04's owner-confirmed v946 Engaging-only resolution controls.
The September 10 review's repeated B7 labels are retained with their topic suffixes
in the JSON, including acceptance omissions repaired by Orders 77-80.

- C12-04/C18-07 owner resolutions: [ORDER_72_SCOPE_PLAN.md](../docs/ORDER_72_SCOPE_PLAN.md), [ORDER_62_SCOPE_PLAN.md](../docs/ORDER_62_SCOPE_PLAN.md).
- Heavy movement and vertical distance: [test_order51_flight.py](../tests/unit/test_order51_flight.py), [test_phase13b_shooting_declarations.py](../tests/unit/test_phase13b_shooting_declarations.py).
- Normal Move occurrence: [test_order80_normal_move.py](../tests/unit/test_order80_normal_move.py).
- Objective control before cleanup: [test_order79_control_first.py](../tests/unit/test_order79_control_first.py).
- Action completed-move interruption: [test_action_movement_interruption.py](../tests/unit/test_action_movement_interruption.py).
- Physical requests and revival replay/redaction: [test_order81_parameterized_projection.py](../tests/unit/test_order81_parameterized_projection.py), [test_order82_revival_engagement.py](../tests/unit/test_order82_revival_engagement.py).

## Complete-game performance

**Unavailable and uncertified: zero complete-game samples.** Mean and maximum are
unknown, not zero. No claim is made against the <60-second mean and ≤300-second
maximum targets. Diagnostic probes and ordinary test durations are not games.

- A versioned complete legal Core workload with concrete rosters, deployment, terrain, seeds and decisions.
- An existing driver or recorded complete game covering parameterized physical proposals through AdapterGameSession, all required decisions and a terminal result.
- Declared reference hardware and per-game results; existing headless adapter protocols and component probes are not a complete-game workload.

## Limits

- All 25 categories, 286 rule/update rows and 59 FAQs were surveyed without stopping at the first defect. A family regression link is not an individual-clause facade proof.
- The 1424 provider-rendered blocks include prose, examples and metadata; they are not claimed to be 1424 independent operative rules.
- Every row retains an explicit open clause-certification status; pending exact source-equivalence and per-clause end-to-end evidence are CAUDIT-01 debt, not automatically 345 gameplay bugs.
- Eight probes across seven finding families reproduce concrete failures/unsupported paths; overhang, random profile values, general ignoring and reserve revival additionally need source-to-facade consumer proofs.
- No finite audit can prove absence of all future defects. No faction, datasheet-specific rule or excluded content is certified.
