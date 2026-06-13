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
- Primary scoring coverage: 3 `engine_implemented`, 22
  `source_known_engine_pending`, 0 `awaiting_source`.
- Primary source-only actions: `decoy-objective`, `triangulate-objective`,
  `extract-intelligence`, `surveil-enemy-unit`,
  `sensor-sweep-locate-and-deny`, `sensor-sweep-extract-relic`, and
  `commit-sabotage`, `secure-asset`, `vanguard-operation`, and
  `maintain-control` are tracked as source descriptors only and are not
  exposed as runtime mission actions.
- Secondary missions: 18 `source_tracked` and `policy_loaded`.
- Secondary scoring rows: 4 fixed policy rows, 20 tactical policy rows, and 28
  source-only branch/procedure rows.
- Tournament fixed secondaries: 4 cards are flagged as fixed-allowed
  (`A Grievous Blow`, `Assassination`, `Bring It Down`,
  `Engage on All Fronts`).

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
| `purge-the-foe` | `purge-the-foe` | Meatgrinder | `primary-meatgrinder` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:more_enemy_units_destroyed_than_friendly_previous_turn`, `engine_primary_condition:control_opponent_home_objective` |
| `purge-the-foe` | `take-and-hold` | Unstoppable Force | `primary-unstoppable-force` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `disruption` | Punishment | `primary-punishment` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_start_turn_choice:condemned_enemy_units`, `engine_primary_condition:condemned_enemy_units_left_battlefield`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:control_opponent_home_objective` |
| `purge-the-foe` | `reconnaissance` | Consecrate | `primary-consecrate` | `implemented` | `source_known_engine_pending` | 5 | 0 | `engine_primary_marker_state:consecrated_objective`, `engine_primary_condition:consecrated_objective_thresholds`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:enemy_home_objective_consecrated` |
| `purge-the-foe` | `priority-assets` | Destroyer's Wrath | `primary-destroyers-wrath` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:more_enemy_units_destroyed_than_friendly_previous_turn` |
| `take-and-hold` | `purge-the-foe` | Immovable Object | `primary-immovable-object` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `take-and-hold` | Battlefield Dominance | `primary-battlefield-dominance` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:control_more_objectives_than_opponent_first_second_rounds`, `engine_primary_condition:each_objective_controlled_from_battle_round_two`, `engine_primary_condition:home_objective_controlled_non_home_objective_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |
| `take-and-hold` | `disruption` | Determined Acquisition | `primary-determined-acquisition` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:each_newly_controlled_non_home_objective_this_turn`, `engine_primary_condition:each_objective_controlled_from_battle_round_two`, `engine_primary_condition:controlled_objective_in_opponent_territory_bonus`, `engine_primary_scoring_grammar:cumulative_condition` |
| `take-and-hold` | `reconnaissance` | Purge and Secure | `primary-purge-and-secure` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:enemy_destroyed_by_friendly_unit_on_objective`, `engine_primary_condition:enemy_started_turn_on_objective_destroyed`, `engine_primary_condition:each_non_home_objective_controlled_from_battle_round_two`, `engine_primary_condition:control_one_or_more_new_non_home_objectives`, `engine_primary_scoring_grammar:exclusive_or_condition` |
| `take-and-hold` | `priority-assets` | Inescapable Dominion | `primary-inescapable-dominion` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_three_or_more_objectives`, `engine_primary_condition:control_two_or_more_objectives_from_battle_round_two`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:control_opponent_home_objective` |
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
| `priority-assets` | `reconnaissance` | Vanguard Operation | `primary-vanguard-operation` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:vanguard-operation`, `engine_primary_condition:friendly_unit_performed_vanguard_operation_this_turn`, `engine_primary_condition:enemy_territory_terrain_area_control`, `engine_primary_condition:control_opponent_home_objective` |
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
| Secure No Man's Land | `secure-no-mans-land` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `control_two_or_more_no_mans_land_objectives_excluding_home` through objective-control records |

## Runtime Caveats

- Event Companion primary matrix identities and layout IDs are implemented, but
  exact per-page terrain and deployment coordinate extraction is still tracked
  separately by layout descriptor source statuses.
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
