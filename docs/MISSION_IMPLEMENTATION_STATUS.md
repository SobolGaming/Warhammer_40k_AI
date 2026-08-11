# Mission Implementation Status

This document tracks the repository's current source and engine status for the
Warhammer Event Companion primary mission matrix and the 11th Edition secondary
missions. It is a tracker, not a source of rules text.

Canonical data lives in code:

- Primary mission matrix cells:
  [`event_primary_mission_matrix_source_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
  and
  [`primary_mission_matrix_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- Primary scoring coverage:
  [`primary_mission_scoring_coverage_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- Mission-card scoring grammar:
  [`mission_card_scoring_grammar()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- Secondary mission source rows:
  [`secondary_mission_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/chapter_approved_2026_27.py),
  imported by the Event Companion mission pack
- Mission action rows:
  [`mission_action_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/chapter_approved_2026_27.py)
  and
  [`primary_mission_action_source_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)

When any source row, engine support, or scoring policy changes, update this file
in the same PR.

## Status Legend

Primary matrix status:

- `implemented`: the matrix cell, primary mission identity, and three layout IDs
  are represented in the Event Companion mission pack.

Primary scoring status:

- `engine_implemented`: source scoring rows exist and the current engine can build
  a scoring policy for that primary mission.
- `source_known_engine_pending`: source scoring rows exist, but one or more
  required engine condition, marker, action, or choice semantics are still
  missing. These paths must remain fail-closed.
- `awaiting_source`: the mission is known from the matrix, but scoring source text
  is not represented yet.

Secondary status:

- `source_tracked`: the secondary card identity and source scoring rows are in the
  mission source package.
- `policy_loaded`: fixed and tactical scoring rows import into
  `MissionScoringPolicy`.
- `state_backed`: the current engine has concrete evidence handling for the
  listed condition family.
- `generic_condition`: the current source row uses a generic
  `fixed_secondary_condition` or `tactical_secondary_condition`; card-specific
  achievement detection still needs focused source and engine work before it can
  be treated as fully implemented.
- `source_only_rows`: exact card branches or When Drawn/definition rows are
  tracked in source data with non-policy `secondary` source kind. They are not
  imported into `MissionScoringPolicy` until the required engine evidence,
  choices, and adapter-visible payloads exist.

## Summary

- Primary matrix cells: 25 of 25 `implemented`.
- Primary scoring coverage: 4 of 25 `engine_implemented`, 21
  `source_known_engine_pending`, 0 `awaiting_source`.
- Primary source-only actions: `decoy-objective`, `triangulate-objective`,
  `extract-intelligence`, `surveil-enemy-unit`,
  `sensor-sweep-locate-and-deny`, `sensor-sweep-extract-relic`, and
  `commit-sabotage`, `secure-asset`, `vanguard-operation`, and
  `maintain-control` are tracked as source descriptors only and are not
  exposed as runtime mission actions.
- Runtime Mission Actions: Death Trap's `booby-trap-terrain`, Terraform's
  `terraform-objective`, Cleanse's `cleanse-objective`, and Plunder's
  `plunder-terrain` are automatically exposed before Shooting-unit selection
  only when the active player owns the applicable Primary or Secondary.
- Secondary missions: 18 `source_tracked` and `policy_loaded`.
- Secondary scoring rows: 4 fixed policy rows, 20 tactical policy rows, and 28
  source-only branch/procedure rows.
- Tournament fixed secondaries: 4 cards are flagged as fixed-allowed
  (`A Grievous Blow`, `Assassination`, `Bring It Down`,
  `Engage on All Fronts`).

## Battlefield Coverage

- Phase 17N has source-hashed executable battlefield packages for all 45 Event
  Companion layouts: all 15 Force Disposition pairings and each pairing's A/B/C
  variants. No layout identity remains geometry-pending.
- The local [Event Companion Battlefield Viewer](BATTLEFIELD_VIEWER.md)
  consumes `battlefield-view-v3-phase17n` directly for every layout. It provides
  an orbitable 3D schematic of classifications, component footprints, walls,
  floors, source-linked objective terrain-area footprints, deployment zones,
  territories, and No Man's Land. Objective identity records remain labels and
  never become inferred marker disks or selectable solids. The viewer never
  falls back to legacy source-row rectangles or image-derived guesses.
- The battlefield contact semantics come from the page-8 Layouts Key, and the
  45 layout diagrams and coordinates are extracted from pages 9-53 of
  `eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf`, whose
  SHA-256 is
  `97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20`.
  The reviewed page-8 key plus pages-9-53 layout extraction SHA-256 is
  `a3e9392adeb52696902a016e3c3529933d1e99f3bfd67069d607410d8e1c137f`,
  the generated artifact SHA-256 is
  `88ba6d7390eab060d6b0c53eb60afbfb1a6813dd80715e3d42562dd0c89128d9`,
  and its canonical package hash is
  `e6671232c7c298befccaf6c6f3000dfc21353830f6ae1a6ca5d10140b344a924`.
  The generator separately pins the stable runtime identity map at
  `742ab841d1ec1e696f4a5c0e3f2e8c251203d510bf1da85fb30af88023cb64f3`.
  The generated `event-companion-battlefields.json` artifact records source
  affines, objective coordinates and bindings, deployment zones, territories,
  No Man's Land, typed Single/Separate terrain-area contacts, and component
  contacts. Its strict loader pins source, extraction, package, and artifact
  hashes and rejects malformed, stale, or re-hashed coordinate drift.
- The package contains 720 physical terrain-area footprint pieces representing
  608 logical rules areas, plus 1,349 individually placed physical components.
  Every layout has 16 footprint pieces. The page-8 key makes 112 two-piece pairs
  into Single logical areas; the remaining 496 pieces are singletons. Page 9,
  Take and Hold versus Take and Hold Layout A, has the source-backed 29-component
  exception because one downed hovercraft has no tall-crate companion; every
  other layout has 30 components. Fourteen shared archetypes define recurring
  component footprints and wall/floor geometry once for reuse throughout the
  package.
- Source terrain-area anchors and component battlefield centers use a
  0.05-inch placement grid. Reviewed mirror placements, asymmetric local
  transforms, and source-indicated area/component contacts remain explicit
  structured data.
  Objective centers retain the source vector extraction's finer 0.01-inch
  precision rather than discarding source accuracy at the terrain-placement
  boundary.
  Every declared contact retains at most one 0.05-inch placement quantum of
  source-fit gap and at most `0.000001` square inches of numerical overlap. Of
  224 declared contacts, 43 have zero recorded gap and 181 retain a source-fit
  open sliver no wider than 0.05 inches: 80 Single and 101 Separate. Of those
  43 zero-gap contacts, 41 also have zero overlap. Two page-12 Single pairs
  have `0.00000087` square inches of overlap after six-decimal geometry
  quantization; every other pair has zero recorded overlap. Single
  contacts share one logical rules identity; Separate contacts remain distinct.
  Neither identity fills source-drawn open board between physical polygons. The
  artifact records every measured runtime gap and overlap.
- Page 29's two paired contacts are the only terrain-area pose witnesses that
  require either adjustment axis to exceed the usual +/-0.20-inch
  canonical-footprint bound. Exhaustive
  evaluation of all four source-pose candidates on the 0.05-inch grid found no
  non-overlapping contact solution through +/-0.30 inches; +/-0.35 inches is
  the first feasible bound. The committed minimum-total corrections are area
  02 `(+0.10, -0.35)`, area 04 `(-0.10, +0.30)`, area 13
  `(+0.05, -0.35)`, and area 15 `(-0.05, +0.30)` inches. The loader permits
  exactly those four reviewed witnesses and retains the 0.20-inch bound for
  every other non-Meatgrinder area.
- Seven component rasters land across their rules-area boundary after source
  quantization. Exhaustive 0.05-inch-grid searches pin only the minimum
  containment corrections: page 23 areas 08 component 03 `(0, -0.05)` and 09
  component 02 `(0, +0.05)`; page 29 areas 04 component 01 `(-0.10, 0)`, 07
  component 01 `(0, +0.05)`, and 13 component 01 `(+0.05, -0.05)`; page 38 area
  02 component 01 `(0, -0.05)`; and page 45 area 02 component 01 `(0, -0.05)`
  inches. Source centers and rotations remain separate provenance fields. All
  84 non-Meatgrinder long-pipe rules proxies use the nearest feasible 0.05-inch
  grid center of their parent footprint because the source raster intentionally
  overhangs that rules area.
- Pages 36 and 46 repeat one Single-area ruin join whose shared rules proxies
  cannot close on the 0.05-inch grid. Exhaustive searches through +/-0.30
  inches prove the minimum exact normal correction is
  `(+0.005440361094, +0.010510105572)` inches, magnitude
  `0.011834688335` inches, applied only to area 10 after its reviewed grid
  placement. The source 0.05-inch anchors remain unchanged in provenance. Four
  source-ID-bound area-pose witnesses form two paired joins: page 36
  `disruption-vs-disruption-layout-1` areas 07 and 10, and page 46
  `reconnaissance-vs-reconnaissance-layout-2` areas 07 and 10. Only the two
  area-10 rows carry the sub-grid delta from `(-0.20, +0.10)`, so their effective
  runtime anchors use 12-decimal precision. This closes both Single joins with
  zero gap and zero overlap without weakening geometry tolerances.
  Intentional clearance between physical terrain and terrain-area edges is
  preserved, as required by the source, rather than treated as missing geometry.
- Meatgrinder's canonical scoring text, source timing, VP values, and structured
  condition tokens are committed separately in
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06_artifacts/primary-meatgrinder-scoring.json`.
  Its package hash is
  `21b3fabcb585ee33b2295a888963d666a42f85d3f09200e973dd7de8253bd39c`
  and its raw artifact SHA-256 is
  `5e892581956e2b3c81bac893caef6b04f71cf19c1c3e2590ea33256b1a786342`.
  The strict loader pins both hashes and records the project-owner-supplied
  official Chapter Approved 2026-27 card transcription reviewed in PR #134 at
  commit `35b9ddaf5`. The GDMissions transcription and card image fetched on
  2026-08-09 are recorded only as non-official secondary corroboration, never as
  GW source authority.
- Verify that the committed battlefield artifact still matches its reviewed
  inputs without writing files with
  `uv run python tools/build_event_companion_battlefields.py --check`.
- Completing all battlefield packages does not promote Primary Mission scoring
  semantics. Every non-Meatgrinder mission already recorded as
  `source_known_engine_pending` remains fail-closed until its engine-owned
  choices, marker state, actions, and scoring conditions exist. Battlefield
  pages are authority for layout facts, not mission-card scoring clauses.
- Component source-image placement and orientation come from reviewed
  source-page affine records. Ruin and non-ruin envelopes use dimensions rounded
  to the 0.05-inch grid and checked against the reviewed source-image spans.
  Component rules polygons and physical wall/floor primitives remain explicit
  engine models rather than traced raster silhouettes. Floor spacing, wall
  heights and thickness, simplified solids, and Dense non-ruin heights remain
  documented engine modeling assumptions; the PDF does not prescribe them.
- Rendering images remain non-authoritative. Runtime setup, movement, collision,
  visibility, and scoring consume the validated structured package, not a page
  image or a renderer-derived measurement.

## Mission-Card Scoring Grammar

| Official Rule Token | Source Status | Engine Contract |
| --- | --- | --- |
| `cumulative_condition` | `source_tracked` | Achieved cumulative branches score together with their normal condition. |
| `exclusive_or_condition` | `source_tracked` | Exclusive OR branches must not be summed for the same card. |
| `exactly_one_condition` | `source_tracked` | Underlined one means exactly one, not one or more. |
| `leaves_battlefield_event` | `source_tracked` | Card-specific evidence must include destroyed, embarked, and rule-removed units before a leaves-battlefield condition can become `state_backed`. |
| `vp_up_to_limit` | `source_tracked`, `engine_guarded` | Rule caps and ledger caps ignore VP above the stated limit. |
| `when_drawn_tactical_only` | `source_tracked` | When Drawn sections apply only to Tactical Secondary Missions and must not affect Fixed Secondary mode. |

## Primary Mission Matrix

| Player Force Disposition | Opponent Force Disposition | Primary Mission | Mission ID | Matrix Status | Scoring Status | Rules | Actions | Needed Work |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |
| `purge-the-foe` | `purge-the-foe` | Meatgrinder | `primary-meatgrinder` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `take-and-hold` | Unstoppable Force | `primary-unstoppable-force` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `disruption` | Punishment | `primary-punishment` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_start_turn_choice:condemned_enemy_units`, `engine_primary_condition:condemned_enemy_units_left_battlefield`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:control_opponent_home_objective_end_of_battle` |
| `purge-the-foe` | `reconnaissance` | Consecrate | `primary-consecrate` | `implemented` | `source_known_engine_pending` | 5 | 0 | `engine_primary_marker_state:consecrated_objective`, `engine_primary_condition:consecrated_objective_thresholds`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:enemy_home_objective_consecrated` |
| `purge-the-foe` | `priority-assets` | Destroyer's Wrath | `primary-destroyers-wrath` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_more_objectives_than_opponent` |
| `take-and-hold` | `purge-the-foe` | Immovable Object | `primary-immovable-object` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `take-and-hold` | Battlefield Dominance | `primary-battlefield-dominance` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:control_more_objectives_than_opponent_first_second_rounds`, `engine_primary_condition:each_objective_controlled_from_battle_round_two`, `engine_primary_condition:home_objective_controlled_non_home_objective_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |
| `take-and-hold` | `disruption` | Determined Acquisition | `primary-determined-acquisition` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:each_newly_controlled_non_home_objective_this_turn`, `engine_primary_condition:each_objective_controlled_from_battle_round_two`, `engine_primary_condition:controlled_objective_in_opponent_territory_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |
| `take-and-hold` | `reconnaissance` | Purge and Secure | `primary-purge-and-secure` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:enemy_destroyed_by_friendly_unit_on_objective`, `engine_primary_condition:enemy_started_turn_on_objective_destroyed`, `engine_primary_condition:each_non_home_objective_controlled_from_battle_round_two`, `engine_primary_condition:control_one_or_more_new_non_home_objectives`, `engine_primary_scoring_grammar:exclusive_or_condition` |
| `take-and-hold` | `priority-assets` | Inescapable Dominion | `primary-inescapable-dominion` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_three_or_more_objectives`, `engine_primary_condition:control_two_or_more_objectives_from_battle_round_two`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:control_opponent_home_objective_end_of_battle` |
| `disruption` | `purge-the-foe` | Delaying Action | `primary-delaying-action` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:each_enemy_unit_destroyed_this_turn`, `engine_primary_condition:control_central_and_expansion_objectives`, `source_objective_role:expansion_objective` |
| `disruption` | `take-and-hold` | Death Trap | `primary-death-trap` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `disruption` | `disruption` | Outmanoeuvre | `primary-outmaneuver` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_enemy_home_objective`, `engine_primary_condition:round_band_objective_control`, `engine_primary_name_alias:outmaneuver_outmanoeuvre` |
| `disruption` | `reconnaissance` | Smoke and Mirrors | `primary-smoke-and-mirrors` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:decoy-objective`, `engine_primary_marker_state:decoy_objective`, `engine_primary_condition:decoy_objective_scoring`, `engine_primary_condition:opponent_territory_objective_bonus` |
| `disruption` | `priority-assets` | Locate and Deny | `primary-locate-and-deny` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_start_battle_setup:locate_and_deny_operation_markers`, `engine_primary_action:sensor-sweep-locate-and-deny`, `engine_primary_marker_state:operation_marker_terrain_area`, `engine_primary_condition:enemy_started_turn_on_objective_destroyed`, `engine_primary_condition:single_friendly_operation_marker_terrain_area_state` |
| `reconnaissance` | `purge-the-foe` | Triangulation | `primary-triangulation` | `implemented` | `source_known_engine_pending` | 5 | 1 | `engine_primary_action:triangulate-objective`, `engine_primary_marker_state:triangulated_objective`, `engine_primary_condition:triangulated_objective_thresholds`, `engine_primary_condition:control_four_or_more_objectives` |
| `reconnaissance` | `take-and-hold` | Reconnaissance Sweep | `primary-reconnaissance-sweep` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:table_quarter_unit_distribution`, `engine_primary_condition:each_enemy_unit_destroyed_this_turn`, `engine_primary_condition:control_one_or_more_non_home_objectives`, `engine_primary_scoring_grammar:exclusive_or_condition` |
| `reconnaissance` | `disruption` | Surveil the Foe | `primary-surveil-the-foe` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:surveil-enemy-unit`, `engine_primary_marker_state:enemy_operation_marker`, `engine_primary_movement_effect:remove_enemy_operation_markers_from_objective`, `engine_primary_condition:enemy_unit_surveilled_marker_exception`, `engine_primary_condition:no_enemy_operation_markers_on_battlefield` |
| `reconnaissance` | `reconnaissance` | Gather Intel | `primary-gather-intel` | `implemented` | `source_known_engine_pending` | 5 | 1 | `engine_primary_action:extract-intelligence`, `engine_primary_marker_state:gather_intel_operation_marker`, `engine_primary_condition:control_one_or_more_central_objectives_first_battle_round`, `engine_primary_condition:each_friendly_unit_extracted_intelligence_this_turn`, `engine_primary_condition:gather_intel_operation_marker_end_of_battle` |
| `reconnaissance` | `priority-assets` | Search and Scour | `primary-search-and-scour` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_one_or_more_central_objectives`, `engine_primary_condition:enemy_started_turn_in_terrain_destroyed`, `engine_primary_condition:each_non_home_objective_controlled_from_battle_round_two`, `engine_primary_condition:no_enemy_units_wholly_within_own_territory` |
| `priority-assets` | `purge-the-foe` | Vital Link | `primary-vital-link` | `implemented` | `source_known_engine_pending` | 5 | 1 | `engine_primary_action:maintain-control`, `engine_primary_marker_state:vital_link_operation_marker`, `engine_primary_condition:central_objective_operation_marker_bonus`, `engine_primary_condition:controlled_central_objective_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |
| `priority-assets` | `take-and-hold` | Secure Asset | `primary-secure-asset` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:secure-asset`, `engine_primary_condition:friendly_unit_secured_asset_this_turn`, `engine_primary_condition:enemy_started_turn_near_central_objective_destroyed`, `engine_primary_condition:control_three_or_more_objectives` |
| `priority-assets` | `disruption` | Extract Relic | `primary-extract-relic` | `implemented` | `source_known_engine_pending` | 5 | 1 | `engine_primary_action:sensor-sweep-extract-relic`, `engine_primary_marker_state:opponent_operation_marker`, `engine_primary_condition:friendly_unit_performed_sensor_sweep_this_turn`, `engine_primary_condition:enemy_started_turn_on_objective_destroyed`, `engine_primary_condition:single_opponent_operation_marker_terrain_area_state` |
| `priority-assets` | `reconnaissance` | Vanguard Operation | `primary-vanguard-operation` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:vanguard-operation`, `engine_primary_condition:friendly_unit_performed_vanguard_operation_this_turn`, `engine_primary_condition:enemy_territory_terrain_area_control`, `engine_primary_condition:control_opponent_home_objective_end_of_battle` |
| `priority-assets` | `priority-assets` | Sabotage | `primary-sabotage` | `implemented` | `source_known_engine_pending` | 3 | 1 | `engine_primary_action:commit-sabotage`, `engine_primary_condition:each_friendly_unit_committed_sabotage_this_turn`, `engine_primary_condition:sabotage_opponent_territory_objective_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |

## Secondary Missions

| Secondary Mission | Mission ID | Availability | Tournament Fixed | Fixed Rules | Tactical Rules | Other Rows | Status | Engine Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| A Grievous Blow | `a-grievous-blow` | `both` | Yes | 1 | 1 | 1 | `source_tracked`, `policy_loaded`, `state_backed`, `source_only_rows` | Tracks `each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn`; When Drawn discard row remains source-only |
| A Tempting Target | `a-tempting-target` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track opponent target selection and target control |
| Assassination | `assassination` | `both` | Yes | 1 | 1 | 4 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track W4+/W3-or-less Character branches and Tactical Character branches |
| Beacon | `beacon` | `tactical` | No | 0 | 1 | 3 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track beacon choice and outside-deployment/territory branches |
| Behind Enemy Lines | `behind-enemy-lines` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track first-round redraw and each-unit scoring |
| Bring It Down | `bring-it-down` | `both` | Yes | 1 | 1 | 1 | `source_tracked`, `policy_loaded`, `state_backed`, `source_only_rows` | Tracks `each_enemy_model_w10_or_more_destroyed_this_turn` with fixed and tactical caps; When Drawn discard row remains source-only |
| Burden of Trust | `burden-of-trust` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track guard selection and guarded-objective scoring |
| Centre Ground | `centre-ground` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track 3VP/5VP centre-distance branches |
| Cleanse | `cleanse` | `tactical` | No | 0 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks objective cleanse counts; runtime action `cleanse-objective` exists |
| Defend Stronghold | `defend-stronghold` | `tactical` | No | 0 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks home objective control and enemy absence from own deployment zone |
| Display of Might | `display-of-might` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track own-turn and opponent-turn No Man's Land unit-count branches |
| Engage on All Fronts | `engage-on-all-fronts` | `both` | Yes | 1 | 1 | 5 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track presence definition and fixed/tactical three-/four-quarter branches |
| Forward Position | `forward-position` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track first-round redraw and forward-objective control |
| No Prisoners | `no-prisoners` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_unit_destroyed_this_turn` |
| Outflank | `outflank` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track one-edge and opposite-edge branches |
| Overwhelming Force | `overwhelming-force` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_unit_started_turn_in_range_of_objective_destroyed` |
| Plunder | `plunder` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks terrain plunder state; runtime action `plunder-terrain` exists |
| Secure No Man's Land | `secure-no-mans-land` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `control_two_or_more_no_mans_land_objectives_excluding_home` through objective-control records filtered to central/No Man's Land objectives |

## Runtime Caveats

- Event Companion primary matrix identities and all layout IDs are implemented.
  All 45 layout descriptors reference source-hashed executable battlefield
  packages. Geometry completion does not change the independently tracked
  Primary Mission scoring status.
- Meatgrinder's four source scoring rows are state-backed, including the
  comparison of enemy units lost during the current scoring player's turn
  against that player's friendly units lost during the opponent's immediately
  prior player turn, plus control of the opponent's home objective from battle
  round two. Scoring evidence records both resolved turn keys, both destruction
  counts and unit IDs, and the opponent-home objective IDs. Unit completion is
  recorded automatically through the shared destruction owner for shooting and
  fight attacks, mortal wounds, direct rule destruction, Desperate Escape,
  end-turn coherency destruction, and emergency-disembark model destruction.
  Reserve-deadline destruction occurs after the player turn has ended and is
  deliberately excluded from this cross-turn comparison. Generic current-turn
  enemy-loss conditions classify records by the destroyed unit's owner and
  active-turn key, so authoritative transition removals count even when no
  destroying player can be attributed.
- Each player-turn boundary records one authoritative, serialized terrain
  snapshot containing every physical unit and the battlefield terrain
  footprints intersected by its models. Automatic destruction copies the
  destroyed component unit's membership from that exact turn snapshot; the
  evidence is always a concrete tuple, including an empty tuple for a unit that
  started outside terrain. Missing snapshots, component rows, or unknown terrain
  fail closed before a destruction record can be created, so Death Trap never
  substitutes destruction-time position or nullable evidence.
- `source_known_engine_pending` primary missions must remain fail-closed until
  the listed conditions, markers, actions, or choices have engine-owned
  validation and mutation paths.
- `decoy-objective`, `triangulate-objective`, `extract-intelligence`,
  `surveil-enemy-unit`, `sensor-sweep-locate-and-deny`,
  `sensor-sweep-extract-relic`, `commit-sabotage`, `secure-asset`,
  `vanguard-operation`, and `maintain-control` are source-only descriptors. Do
  not expose them through
  `MissionPackDefinition.mission_action(...)` or Shooting-phase mission action
  start until their validation, marker state, and scoring semantics exist.
- Secondary lifecycle support exists for source rows, fixed/tactical modes,
  tactical draw, scoring, retain/discard, Fixed card states that remain active
  after scoring, the 20 VP per Fixed Mission card cap, state-backed awards, and
  source-only branch/procedure rows. Individual card achievement semantics still
  need card-specific tests before moving from `generic_condition` or
  `source_only_rows` to `state_backed`.
