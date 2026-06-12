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

## Summary

- Primary matrix cells: 25 of 25 `implemented`.
- Primary scoring coverage: 3 `engine_implemented`, 8
  `source_known_engine_pending`, 14 `awaiting_source`.
- Primary source-only actions: `decoy-objective` and `triangulate-objective` are
  tracked as source descriptors only and are not exposed as runtime mission
  actions.
- Secondary missions: 20 `source_tracked` and `policy_loaded`.
- Secondary scoring rows: 6 fixed rows, 22 tactical rows, and 10 alternate or
  partial rows.
- Tournament fixed secondaries: 4 cards are flagged as fixed-allowed
  (`Assassination`, `Bring It Down`, `Cleanse`, `Cull the Horde`).

## Primary Mission Matrix

| Player Force Disposition | Opponent Force Disposition | Primary Mission | Mission ID | Matrix Status | Scoring Status | Rules | Actions | Needed Work |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |
| `purge-the-foe` | `purge-the-foe` | Meatgrinder | `primary-meatgrinder` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:more_enemy_units_destroyed_than_friendly_previous_turn`, `engine_primary_condition:control_opponent_home_objective` |
| `purge-the-foe` | `take-and-hold` | Unstoppable Force | `primary-unstoppable-force` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `disruption` | Punishment | `primary-punishment` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_start_turn_choice:condemned_enemy_units`, `engine_primary_condition:condemned_enemy_units_left_battlefield`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:control_opponent_home_objective` |
| `purge-the-foe` | `reconnaissance` | Consecrate | `primary-consecrate` | `implemented` | `source_known_engine_pending` | 5 | 0 | `engine_primary_marker_state:consecrated_objective`, `engine_primary_condition:consecrated_objective_thresholds`, `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:enemy_home_objective_consecrated` |
| `purge-the-foe` | `priority-assets` | Destroyer's Wrath | `primary-destroyers-wrath` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_more_objectives_than_opponent`, `engine_primary_condition:more_enemy_units_destroyed_than_friendly_previous_turn` |
| `take-and-hold` | `purge-the-foe` | Immovable Object | `primary-immovable-object` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `take-and-hold` | Battlefield Dominance | `primary-battlefield-dominance` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `take-and-hold` | `disruption` | Determined Acquisition | `primary-determined-acquisition` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `take-and-hold` | `reconnaissance` | Purge and Secure | `primary-purge-and-secure` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `take-and-hold` | `priority-assets` | Inescapable Dominion | `primary-inescapable-dominion` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `disruption` | `purge-the-foe` | Delaying Action | `primary-delaying-action` | `implemented` | `source_known_engine_pending` | 3 | 0 | `engine_primary_condition:each_enemy_unit_destroyed_this_turn`, `engine_primary_condition:control_central_and_expansion_objectives`, `source_objective_role:expansion_objective` |
| `disruption` | `take-and-hold` | Death Trap | `primary-death-trap` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `disruption` | `disruption` | Outmanoeuvre | `primary-outmaneuver` | `implemented` | `source_known_engine_pending` | 4 | 0 | `engine_primary_condition:control_enemy_home_objective`, `engine_primary_condition:round_band_objective_control`, `engine_primary_name_alias:outmaneuver_outmanoeuvre` |
| `disruption` | `reconnaissance` | Smoke and Mirrors | `primary-smoke-and-mirrors` | `implemented` | `source_known_engine_pending` | 4 | 1 | `engine_primary_action:decoy-objective`, `engine_primary_marker_state:decoy_objective`, `engine_primary_condition:decoy_objective_scoring`, `engine_primary_condition:opponent_territory_objective_bonus` |
| `disruption` | `priority-assets` | Locate and Deny | `primary-locate-and-deny` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `reconnaissance` | `purge-the-foe` | Triangulation | `primary-triangulation` | `implemented` | `source_known_engine_pending` | 5 | 1 | `engine_primary_action:triangulate-objective`, `engine_primary_marker_state:triangulated_objective`, `engine_primary_condition:triangulated_objective_thresholds`, `engine_primary_condition:control_four_or_more_objectives` |
| `reconnaissance` | `take-and-hold` | Reconnaissance Sweep | `primary-reconnaissance-sweep` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `reconnaissance` | `disruption` | Surveil the Foe | `primary-surveil-the-foe` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `reconnaissance` | `reconnaissance` | Gather Intel | `primary-gather-intel` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `reconnaissance` | `priority-assets` | Search and Scour | `primary-search-and-scour` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `priority-assets` | `purge-the-foe` | Vital Link | `primary-vital-link` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `priority-assets` | `take-and-hold` | Secure Asset | `primary-secure-asset` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `priority-assets` | `disruption` | Extract Relic | `primary-extract-relic` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `priority-assets` | `reconnaissance` | Vanguard Operation | `primary-vanguard-operation` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |
| `priority-assets` | `priority-assets` | Sabotage | `primary-sabotage` | `implemented` | `awaiting_source` | 0 | 0 | `source_primary_scoring_text` |

## Secondary Missions

| Secondary Mission | Mission ID | Availability | Tournament Fixed | Fixed Rules | Tactical Rules | Other Rows | Status | Engine Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| A Tempting Target | `a-tempting-target` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded` | `generic_condition` |
| Area Denial | `area-denial` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Assassination | `assassination` | `both` | Yes | 1 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Behind Enemy Lines | `behind-enemy-lines` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Bring It Down | `bring-it-down` | `both` | Yes | 1 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_model_w10_or_more_destroyed_this_turn` |
| Cleanse | `cleanse` | `both` | Yes | 2 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks objective cleanse counts; runtime action `cleanse-objective` exists |
| Cull the Horde | `cull-the-horde` | `both` | Yes | 1 | 1 | 0 | `source_tracked`, `policy_loaded` | `generic_condition` |
| Defend Stronghold | `defend-stronghold` | `tactical` | No | 0 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks home objective control and enemy absence from own deployment zone |
| Display of Might | `display-of-might` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded` | `generic_condition` |
| Engage on All Fronts | `engage-on-all-fronts` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Establish Locus | `establish-locus` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; runtime action `establish-locus-objective` exists; alternate or partial row present |
| Extend Battle Lines | `extend-battle-lines` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Marked for Death | `marked-for-death` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| No Prisoners | `no-prisoners` | `both` | No | 1 | 1 | 0 | `source_tracked`, `policy_loaded` | `generic_condition`; source has fixed and tactical rows but this card is not tournament fixed-allowed |
| Overwhelming Force | `overwhelming-force` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_unit_started_turn_on_objective_destroyed` |
| Plunder | `plunder` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks terrain plunder state; runtime action `plunder-terrain` exists |
| Recover Assets | `recover-assets` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; runtime action `recover-assets-objective` exists; alternate or partial row present |
| Sabotage | `sabotage` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; runtime action `sabotage-terrain` exists; alternate or partial row present |
| Secure No Man's Land | `secure-no-mans-land` | `tactical` | No | 0 | 1 | 1 | `source_tracked`, `policy_loaded` | `generic_condition`; alternate or partial row present |
| Storm Hostile Objective | `storm-hostile-objective` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded` | `generic_condition` |

## Runtime Caveats

- Event Companion primary matrix identities and layout IDs are implemented, but
  exact per-page terrain and deployment coordinate extraction is still tracked
  separately by layout descriptor source statuses.
- `source_known_engine_pending` primary missions must remain fail-closed until
  the listed conditions, markers, actions, or choices have engine-owned
  validation and mutation paths.
- `decoy-objective` and `triangulate-objective` are source-only descriptors. Do
  not expose them through `MissionPackDefinition.mission_action(...)` or
  Shooting-phase mission action start until their validation, marker state, and
  scoring semantics exist.
- Secondary lifecycle support exists for source rows, fixed/tactical modes,
  tactical draw, scoring, retain/discard, and state-backed awards. Individual
  card achievement semantics still need card-specific tests before moving from
  `generic_condition` to `state_backed`.
