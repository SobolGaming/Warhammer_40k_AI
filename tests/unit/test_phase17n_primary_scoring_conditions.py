from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    ObjectiveMarkerModelWitness,
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    primary_unattributed_destruction_cause_from_token,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    home_objective_ids,
    opponent_home_control_evidence,
    primary_score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    TABLE_QUARTER_IDS,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_primary_victory_point_award,
    validate_primary_victory_point_transaction,
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="module")
def battlefield_dominance_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        terrain_layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


@pytest.fixture(scope="module")
def purge_and_secure_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
        terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="reconnaissance",
    )


def test_promoted_objective_conditions_use_exact_control_and_directed_geometry(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    ids_by_suffix = {
        marker.objective_marker_id.rsplit("-", maxsplit=1)[-1]: marker.objective_marker_id
        for marker in setup.objective_markers
    }
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    defender_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("defender-home")
    )
    controlled_by_a = (
        attacker_home_id,
        ids_by_suffix["central"],
        ids_by_suffix["east"],
        defender_home_id,
    )
    controlled_by_b = (ids_by_suffix["west"],)
    record = _control_record(
        setup,
        battle_round=2,
        controlled_by_a=controlled_by_a,
        controlled_by_b=controlled_by_b,
    )
    opponent_territory_ids = _territory_objective_ids(
        setup,
        owner_role="defender",
    )
    spatial = _spatial_evidence(
        record=record,
        opponent_territory_ids=opponent_territory_ids,
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        turn_start_controlled_objective_ids=(attacker_home_id, ids_by_suffix["central"]),
        spatial_evidence=spatial,
    )

    expected_counts = {
        "control_more_objectives_than_opponent_first_and_second_battle_round": 1,
        "each_objective_controlled_from_battle_round_two": 4,
        "each_controlled_objective_from_battle_round_two": 4,
        "each_non_home_objective_controlled_if_home_objective_controlled": 3,
        "control_one_or_more_non_home_objectives_from_battle_round_two": 1,
        "control_central_and_expansion_objectives": 1,
        "each_newly_controlled_non_home_objective_this_turn": 2,
        "each_controlled_objective_in_opponent_territory": len(
            set(controlled_by_a).intersection(opponent_territory_ids)
        ),
        "control_three_or_more_objectives": 1,
        "control_two_or_more_objectives_from_battle_round_two": 1,
        "control_more_objectives_than_opponent_from_battle_round_two": 1,
        "control_enemy_home_objective": 1,
        "each_non_home_objective_controlled_battle_rounds_two_and_three": 3,
        "control_one_or_more_central_objectives": 1,
        "each_non_home_objective_controlled_from_battle_round_two": 3,
    }
    for condition, expected_count in expected_counts.items():
        evidence = evaluate_primary_scoring_condition(
            condition=condition,
            context=context,
        )
        assert evidence["score_count"] == expected_count, condition

    territory_evidence = evaluate_primary_scoring_condition(
        condition="each_controlled_objective_in_opponent_territory",
        context=context,
    )
    assert territory_evidence["opponent_player_id"] == "player-b"
    assert territory_evidence["opponent_territory_objective_ids"] == list(opponent_territory_ids)


def test_battlefield_dominance_cumulative_grammar_scores_through_policy(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("central")
    )
    east_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("east")
    )
    west_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("west")
    )
    record = _control_record(
        setup,
        battle_round=2,
        controlled_by_a=(attacker_home_id, central_id, east_id),
        controlled_by_b=(west_id,),
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )
    policies = mission_scoring_policies_from_setup(setup)
    assert MissionScoringPolicies.from_payload(policies.to_payload()) == policies

    round_one_awards = policies.primary_awards_from_objective_control(
        record=replace(record, battle_round=1),
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        turn_start_states=(),
        terrain_trap_states=(),
        unit_destruction_states=(),
    )
    assert round_one_awards == ()

    awards = policies.primary_awards_from_objective_control(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        turn_start_states=(),
        terrain_trap_states=(),
        unit_destruction_states=(),
    )

    assert {
        cast(dict[str, object], award.metadata)["scoring_rule_id"]: award.amount for award in awards
    } == {
        "battlefield-dominance-each-objective": 9,
        "battlefield-dominance-home-controlled-non-home-bonus": 4,
    }
    assert all(
        cast(dict[str, object], award.metadata)["primary_scoring_selected_rule_ids"]
        == [
            "battlefield-dominance-each-objective",
            "battlefield-dominance-home-controlled-non-home-bonus",
        ]
        for award in awards
    )


def test_primary_policy_rejects_forged_end_of_battle_and_foreign_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    policies = mission_scoring_policies_from_setup(setup)
    policy = policies.policy_for_player("player-a")
    command_record = _control_record(
        setup,
        battle_round=2,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )

    with pytest.raises(GameLifecycleError, match="last player's turn-end record"):
        policies.primary_awards_from_objective_control(
            record=_control_record(setup, battle_round=5),
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(),
            scoring_player_ids=("player-a", "player-b"),
            end_of_battle=True,
        )

    foreign_turn_start = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:foreign",
        game_id="primary-game:foreign",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=replace(
            command_record,
            record_id="primary-turn-start-control:foreign",
            game_id="primary-game:foreign",
            timing=ObjectiveControlTiming.TURN_START,
        ),
        controlled_objective_ids=(),
        source_id="primary-turn-start:foreign",
    )
    foreign_trap = PrimaryTerrainTrapState(
        trap_id="primary-terrain-trap:foreign",
        game_id="primary-game:foreign",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        terrain_feature_id="terrain-area:foreign",
        is_objective=False,
        action_id="primary-action:foreign",
        source_id="primary-terrain-trap:foreign",
    )
    foreign_destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:foreign",
        game_id="primary-game:foreign",
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=("primary-departure:foreign",),
        unattributed_cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
        source_mutation_id="end-turn-cleanup:foreign",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        destroyed_unit_instance_id="enemy-unit:foreign",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
        source_id="primary-destruction:foreign",
    )

    with pytest.raises(GameLifecycleError, match="turn-start evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(foreign_turn_start,),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="terrain-trap evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(foreign_trap,),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="destruction evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(foreign_destruction,),
        )

    with pytest.raises(GameLifecycleError, match="cannot come from a future battle round"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(
                replace(
                    foreign_turn_start,
                    game_id=command_record.game_id,
                    battle_round=3,
                    source_objective_control_record=replace(
                        foreign_turn_start.source_objective_control_record,
                        game_id=command_record.game_id,
                        battle_round=3,
                    ),
                ),
            ),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="references an unknown player"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(
                replace(
                    foreign_destruction,
                    game_id=command_record.game_id,
                    destroyed_player_id="player-unknown",
                ),
            ),
        )


def test_exact_thirteen_implemented_primaries_build_typed_runtime_rules() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    implemented_ids = {
        "primary-battlefield-dominance",
        "primary-death-trap",
        "primary-delaying-action",
        "primary-destroyers-wrath",
        "primary-determined-acquisition",
        "primary-immovable-object",
        "primary-inescapable-dominion",
        "primary-meatgrinder",
        "primary-outmaneuver",
        "primary-purge-and-secure",
        "primary-reconnaissance-sweep",
        "primary-search-and-scour",
        "primary-unstoppable-force",
    }
    primary_by_id = {
        primary.primary_mission_id: primary for primary in mission_pack.primary_missions
    }

    for primary_mission_id in sorted(implemented_ids):
        rules = primary_scoring_rules_from_definition(primary_by_id[primary_mission_id])
        assert rules
        assert (
            tuple(PrimaryMissionScoringRule.from_payload(rule.to_payload()) for rule in rules)
            == rules
        )

    assert {
        primary.primary_mission_id
        for primary in mission_pack.primary_missions
        if primary_scoring_rules_from_definition(primary, require_supported=False)
    } == implemented_ids


def test_promoted_destruction_and_table_quarter_conditions_emit_witnesses(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    record = _control_record(setup, battle_round=2)
    destruction_evidence = (
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:enemy-one",
            battle_round=2,
            active_player_id="player-a",
            destroying_player_id=None,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:one",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=("terrain-area:alpha",),
            started_turn_objective_marker_ids=(),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:enemy-two",
            battle_round=2,
            active_player_id="player-a",
            destroying_player_id=None,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:two",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=(),
            started_turn_objective_marker_ids=(),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:friendly-previous",
            battle_round=1,
            active_player_id="player-b",
            destroying_player_id=None,
            destroyed_player_id="player-a",
            destroyed_unit_instance_id="friendly-unit:previous",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=(),
            started_turn_objective_marker_ids=(),
        ),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=destruction_evidence,
        spatial_evidence=_spatial_evidence(
            record=record,
            opponent_territory_ids=_territory_objective_ids(
                setup,
                owner_role="defender",
            ),
        ),
    )

    each_destroyed = evaluate_primary_scoring_condition(
        condition="each_enemy_unit_destroyed_this_turn",
        context=context,
    )
    comparison = evaluate_primary_scoring_condition(
        condition="more_enemy_units_destroyed_than_friendly_previous_turn",
        context=context,
    )
    terrain_destruction = evaluate_primary_scoring_condition(
        condition="one_or_more_enemy_units_started_turn_in_terrain_area_destroyed_this_turn",
        context=context,
    )
    three_quarters = evaluate_primary_scoring_condition(
        condition=(
            "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
            "not_within_six_of_center"
        ),
        context=context,
    )
    four_quarters = evaluate_primary_scoring_condition(
        condition=(
            "four_or_more_friendly_units_wholly_within_four_different_table_quarters_"
            "not_within_six_of_center"
        ),
        context=context,
    )

    assert each_destroyed["score_count"] == 2
    assert each_destroyed["destruction_ids"] == [
        "destruction:enemy-one",
        "destruction:enemy-two",
    ]
    assert comparison["score_count"] == 1
    assert comparison["enemy_units_destroyed"] == 2
    assert comparison["friendly_units_destroyed"] == 1
    assert terrain_destruction["score_count"] == 1
    assert terrain_destruction["started_turn_terrain_feature_ids"] == ["terrain-area:alpha"]
    assert three_quarters["score_count"] == 1
    assert four_quarters["score_count"] == 1
    assert four_quarters["qualifying_table_quarter_ids"] == sorted(TABLE_QUARTER_IDS)
    assert len(cast(list[object], four_quarters["table_quarter_unit_witnesses"])) == 4


def test_friendly_attributed_source_on_objective_requires_exact_typed_witness(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    source_rules_unit_id = "friendly-rules-unit:source"
    source_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id="friendly-model:source",
    )
    source_on_objective = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id=central_id,
                model_instance_ids=("friendly-model:source",),
            ),
        ),
    )
    qualifying = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:attributed-on-objective",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="enemy-unit:qualifying",
        destruction_attribution=source_attribution,
        source_rules_unit_objective_proximity_witness=source_on_objective,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=(qualifying,),
    )

    evidence = evaluate_primary_scoring_condition(
        condition=("one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn"),
        context=context,
    )

    assert evidence["score_count"] == 1
    assert evidence["destruction_ids"] == ["destruction:attributed-on-objective"]
    assert evidence["destroyed_unit_instance_ids"] == ["enemy-unit:qualifying"]
    assert evidence["source_rules_unit_objective_marker_ids"] == [central_id]

    empty_source_witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:source",),
        objective_marker_witnesses=(),
    )
    player_only_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    non_qualifying = {
        "typed-empty-witness": replace(
            qualifying,
            destruction_id="destruction:typed-empty-witness",
            source_rules_unit_objective_proximity_witness=empty_source_witness,
        ),
        "player-only-attribution": replace(
            qualifying,
            destruction_id="destruction:player-only-attribution",
            destruction_attribution=player_only_attribution,
            source_rules_unit_objective_proximity_witness=None,
        ),
        "unattributed": replace(
            qualifying,
            destruction_id="destruction:unattributed",
            destroying_player_id=None,
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
        ),
        "self-owned-target": replace(
            qualifying,
            destruction_id="destruction:self-owned-target",
            destroyed_player_id="player-a",
        ),
    }
    for case_id, row in non_qualifying.items():
        rejected = evaluate_primary_scoring_condition(
            condition=("one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn"),
            context=replace(context, destruction_evidence=(row,)),
        )
        assert rejected["score_count"] == 0, case_id
        assert rejected["destruction_ids"] == [], case_id


def test_started_turn_objective_destruction_is_attribution_independent_and_central_filtered(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    non_central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is not ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    central_destruction = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:started-central",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="enemy-unit:started-central",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(central_id,),
    )
    non_central_destruction = replace(
        central_destruction,
        destruction_id="destruction:started-non-central",
        destroyed_unit_instance_id="enemy-unit:started-non-central",
        started_turn_objective_marker_ids=(non_central_id,),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=(central_destruction, non_central_destruction),
    )

    any_objective = evaluate_primary_scoring_condition(
        condition=("one_or_more_enemy_units_started_turn_within_objective_destroyed_this_turn"),
        context=context,
    )
    central_only = evaluate_primary_scoring_condition(
        condition=(
            "one_or_more_enemy_units_started_turn_within_central_objective_range_"
            "destroyed_this_turn"
        ),
        context=context,
    )

    assert any_objective["score_count"] == 1
    assert any_objective["destruction_ids"] == [
        "destruction:started-central",
        "destruction:started-non-central",
    ]
    assert any_objective["started_turn_objective_marker_ids"] == sorted(
        (central_id, non_central_id)
    )
    assert central_only["score_count"] == 1
    assert central_only["destruction_ids"] == ["destruction:started-central"]
    assert central_only["started_turn_objective_marker_ids"] == [central_id]
    assert central_only["central_objective_marker_ids"] == [central_id]


def test_purge_and_secure_equal_destruction_branches_award_one_three_vp_result(
    purge_and_secure_setup: MissionSetup,
) -> None:
    setup = purge_and_secure_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    source_rules_unit_id = "friendly-rules-unit:purge-source"
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id="friendly-model:purge-source",
    )
    source_witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:purge-source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id=central_id,
                model_instance_ids=("friendly-model:purge-source",),
            ),
        ),
    )
    destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:purge-both-branches",
        game_id=record.game_id,
        destroying_player_id="player-a",
        destruction_attribution=attribution,
        source_model_destroyed_event_id="event:model-destroyed:purge-both-branches",
        source_rules_unit_objective_proximity_witness=source_witness,
        source_battlefield_departure_ids=("primary-departure:purge-both-branches",),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.FIGHT.value,
        destroyed_unit_instance_id="enemy-unit:purge-target",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(central_id,),
        source_id="primary-destruction:purge-both-branches",
    )
    turn_start = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:purge-player-a:round-2",
        game_id=record.game_id,
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=replace(
            record,
            record_id="primary-turn-start-control:purge-player-a:round-2",
            timing=ObjectiveControlTiming.TURN_START,
        ),
        controlled_objective_ids=(),
        source_id="primary-turn-start:purge-player-a:round-2",
    )
    policies = mission_scoring_policies_from_setup(setup)

    awards = policies.primary_awards_from_objective_control(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        turn_start_states=(turn_start,),
        terrain_trap_states=(),
        unit_destruction_states=(destruction,),
    )

    assert len(awards) == 1
    (award,) = awards
    assert award.amount == 3
    assert award.source_id == "primary-purge-and-secure"
    metadata = cast(dict[str, object], award.metadata)
    assert metadata["scoring_rule_id"] == ("purge-and-secure-destroyed-by-objective-unit-turn-end")
    assert metadata["primary_scoring_achieved_rule_ids"] == [
        "purge-and-secure-destroyed-by-objective-unit-turn-end",
        "purge-and-secure-started-objective-destroyed-turn-end",
    ]
    assert metadata["primary_scoring_selected_rule_ids"] == [
        "purge-and-secure-destroyed-by-objective-unit-turn-end"
    ]
    assert metadata["primary_scoring_suppressed_rule_ids"] == [
        "purge-and-secure-started-objective-destroyed-turn-end"
    ]


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("source_kind", "Primary VP policy validation requires a Primary source row"),
        ("player", "Primary VP policy player_id drift"),
        (
            "source_id",
            "Primary VP source does not match the player's assigned Primary mission",
        ),
        ("metadata", "Primary VP metadata must be an object"),
        ("missing_rule_id", "Primary VP metadata requires scoring_rule_id"),
        (
            "unknown_rule_id",
            "Primary VP scoring_rule_id does not identify an assigned Primary scoring rule",
        ),
        (
            "rule_source",
            "Primary VP scoring_rule_source_id drifted from policy",
        ),
        (
            "rule_condition",
            "Primary VP scoring_rule_condition drifted from policy",
        ),
        ("score_count", "Primary VP metadata requires positive score_count"),
        (
            "points_per_count_missing",
            "Primary VP metadata requires positive victory_points_per_count",
        ),
        (
            "points_per_count_drift",
            "Primary VP victory_points_per_count drifted from policy",
        ),
        ("amount", "Primary VP amount drifted from scoring-rule arithmetic"),
        ("capped_amount", "Primary VP amount drifted from scoring-rule arithmetic"),
        (
            "boundary_missing",
            "Primary VP objective_control_record_id does not identify an authoritative boundary",
        ),
        (
            "boundary_identity",
            "Primary VP objective-control boundary identity drifted",
        ),
        ("row_boundary", "Primary VP row drifted from its objective-control boundary"),
        ("active_player", "Primary VP boundary drifted from the active player"),
        ("source_timing", "Primary VP scoring_timing drifted from its source rule"),
        (
            "boundary_timing",
            "Primary VP scoring_timing drifted from its objective-control boundary",
        ),
        (
            "other_player_boundary",
            "Ordinary Primary VP scoring requires the assigned player's boundary",
        ),
        (
            "round_one_boundary",
            "Primary VP scoring rule does not apply at its objective-control boundary",
        ),
        ("cap_audit", "Primary VP awards must not contain a VP cap audit"),
    ],
)
def test_primary_victory_point_award_validation_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    policy, boundary, award = _primary_vp_policy_fixture(battlefield_dominance_setup)
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    boundaries = (boundary,)
    expected_active_player = boundary.active_player_id

    if corruption == "source_kind":
        award = replace(award, source_kind=VictoryPointSourceKind.FIXED_SECONDARY)
    elif corruption == "player":
        award = replace(award, player_id="player-b")
    elif corruption == "source_id":
        award = replace(award, source_id="primary:forged")
    elif corruption == "metadata":
        award = replace(award, metadata=None)
    elif corruption == "missing_rule_id":
        metadata.pop("scoring_rule_id")
    elif corruption == "unknown_rule_id":
        metadata["scoring_rule_id"] = "rule:forged"
    elif corruption == "rule_source":
        metadata["scoring_rule_source_id"] = "source:forged"
    elif corruption == "rule_condition":
        metadata["scoring_rule_condition"] = "condition:forged"
    elif corruption == "score_count":
        metadata["score_count"] = 0
    elif corruption == "points_per_count_missing":
        metadata["victory_points_per_count"] = None
    elif corruption == "points_per_count_drift":
        metadata["victory_points_per_count"] = 99
    elif corruption == "amount":
        award = replace(award, amount=award.amount + 1)
    elif corruption == "capped_amount":
        policy = replace(
            policy,
            primary_scoring_rules=tuple(
                replace(rule, cap=award.amount - 1)
                if rule.rule_id == metadata["scoring_rule_id"]
                else rule
                for rule in policy.primary_scoring_rules
            ),
        )
    elif corruption == "boundary_missing":
        metadata["objective_control_record_id"] = "boundary:missing"
    elif corruption == "boundary_identity":
        boundary = replace(boundary, record_id="boundary:forged")
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
    elif corruption == "row_boundary":
        award = replace(award, phase=BattlePhase.FIGHT.value)
    elif corruption == "active_player":
        expected_active_player = "player-b"
    elif corruption == "source_timing":
        award = replace(award, scoring_timing="end_of_battle")
    elif corruption == "boundary_timing":
        award = replace(award, scoring_timing=ObjectiveControlTiming.TURN_END.value)
    elif corruption == "other_player_boundary":
        boundary = replace(
            boundary,
            record_id=(
                f"objective-control:round-{boundary.battle_round:02d}:player-b:"
                f"{boundary.phase}:{boundary.timing.value}"
            ),
            active_player_id="player-b",
        )
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
        expected_active_player = "player-b"
    elif corruption == "round_one_boundary":
        boundary = replace(
            boundary,
            record_id=(
                f"objective-control:round-01:{boundary.active_player_id}:"
                f"{boundary.phase}:{boundary.timing.value}"
            ),
            battle_round=1,
        )
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
        award = replace(award, battle_round=1)
    elif corruption == "cap_audit":
        metadata["vp_cap_audit"] = {
            "requested_amount": award.amount,
            "applied_amount": award.amount,
        }
    else:
        raise AssertionError(f"unsupported Primary VP corruption: {corruption}")
    if corruption not in {"metadata", "source_kind", "player", "source_id"}:
        award = replace(award, metadata=metadata)

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_victory_point_award(
            policy=policy,
            award=award,
            objective_control_records=boundaries,
            turn_order=("player-a", "player-b"),
            expected_boundary_active_player_id=expected_active_player,
        )


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("witnesses_not_list", "objective_marker_witnesses must be a list"),
        ("payload_not_object", "payload must be an object"),
        ("non_string_key", "payload must be an object"),
        ("empty_model_ids", "model_instance_ids must not be empty"),
        ("duplicate_model_ids", "model_instance_ids must not contain duplicates"),
        ("components_not_list", "component_unit_instance_ids must be a list"),
        ("empty_component_ids", "component_unit_instance_ids must not be empty"),
        (
            "duplicate_objective",
            "objective_marker_witnesses must be unique per objective marker",
        ),
        ("payload_fields", "RulesUnitObjectiveProximityWitness payload fields are invalid"),
    ],
)
def test_objective_proximity_witness_payload_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit:source",
        component_unit_instance_ids=("unit:source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective:source",
                model_instance_ids=("model:source",),
            ),
        ),
    )
    payload = deepcopy(cast(dict[str, JsonValue], witness.to_payload()))
    assert RulesUnitObjectiveProximityWitness.from_payload(payload) == witness
    raw_witnesses = cast(list[dict[str, JsonValue]], payload["objective_marker_witnesses"])
    if corruption == "witnesses_not_list":
        payload["objective_marker_witnesses"] = None
    elif corruption == "payload_not_object":
        payload = cast(dict[str, JsonValue], None)
    elif corruption == "non_string_key":
        cast(dict[object, JsonValue], payload)[1] = True
    elif corruption == "empty_model_ids":
        raw_witnesses[0]["model_instance_ids"] = []
    elif corruption == "duplicate_model_ids":
        raw_witnesses[0]["model_instance_ids"] = ["model:source", "model:source"]
    elif corruption == "components_not_list":
        payload["component_unit_instance_ids"] = None
    elif corruption == "empty_component_ids":
        payload["component_unit_instance_ids"] = []
    elif corruption == "duplicate_objective":
        raw_witnesses.append(deepcopy(raw_witnesses[0]))
    elif corruption == "payload_fields":
        payload["forged"] = True
    else:
        raise AssertionError(f"unsupported proximity witness corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        RulesUnitObjectiveProximityWitness.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("component_ids_not_tuple", "component_unit_instance_ids must be a tuple"),
        ("witnesses_not_tuple", "objective_marker_witnesses must be a tuple"),
        ("untyped_witness", "objective_marker_witnesses must contain typed witnesses"),
    ],
)
def test_objective_proximity_witness_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    objective_witnesses: object = []
    component_ids: object = ("unit:source",)
    if corruption == "untyped_witness":
        objective_witnesses = (object(),)
    elif corruption == "component_ids_not_tuple":
        component_ids = []

    with pytest.raises(GameLifecycleError, match=expected_error):
        RulesUnitObjectiveProximityWitness(
            rules_unit_instance_id="rules-unit:source",
            component_unit_instance_ids=cast(tuple[str, ...], component_ids),
            objective_marker_witnesses=cast(
                tuple[ObjectiveMarkerModelWitness, ...],
                objective_witnesses,
            ),
        )


@pytest.mark.parametrize(
    ("token", "expected_error"),
    [
        (None, "Primary unattributed destruction cause must be a string"),
        ("forged", "Primary unattributed destruction cause is unsupported"),
    ],
)
def test_primary_unattributed_destruction_cause_token_fails_closed(
    token: object,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        primary_unattributed_destruction_cause_from_token(token)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("unattributed_destroyer", "cannot identify a destroyer"),
        ("destroyer_drift", "destroying-player attribution drift"),
        ("player_only_witness", "cannot carry a source-unit objective witness"),
        ("source_witness_missing", "requires its exact objective proximity witness"),
        ("terrain_ids_not_tuple", "started_turn_terrain_feature_ids must be a tuple"),
        ("terrain_ids_duplicate", "started_turn_terrain_feature_ids must not contain duplicates"),
        ("untyped_attribution", "attribution must be ModelDestructionAttribution"),
        ("untyped_witness", "source objective witness must be typed"),
        ("battle_round", "battle_round must be a positive integer"),
    ],
)
def test_primary_unit_destruction_evidence_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    player_only = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    source_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id="rules-unit:source",
        source_model_instance_id="model:source",
    )
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit:source",
        component_unit_instance_ids=("unit:source",),
        objective_marker_witnesses=(),
    )
    parameters: dict[str, Any] = {
        "destruction_id": "destruction:validation",
        "battle_round": 2,
        "active_player_id": "player-a",
        "destroying_player_id": None,
        "destroyed_player_id": "player-b",
        "destroyed_unit_instance_id": "unit:destroyed",
        "destruction_attribution": None,
        "source_rules_unit_objective_proximity_witness": None,
        "started_turn_terrain_feature_ids": (),
        "started_turn_objective_marker_ids": (),
    }
    if corruption == "unattributed_destroyer":
        parameters["destroying_player_id"] = "player-a"
    elif corruption == "destroyer_drift":
        parameters["destroying_player_id"] = "player-b"
        parameters["destruction_attribution"] = player_only
    elif corruption == "player_only_witness":
        parameters["destroying_player_id"] = "player-a"
        parameters["destruction_attribution"] = player_only
        parameters["source_rules_unit_objective_proximity_witness"] = witness
    elif corruption == "source_witness_missing":
        parameters["destroying_player_id"] = "player-a"
        parameters["destruction_attribution"] = source_attribution
    elif corruption == "terrain_ids_not_tuple":
        parameters["started_turn_terrain_feature_ids"] = []
    elif corruption == "terrain_ids_duplicate":
        parameters["started_turn_terrain_feature_ids"] = ("terrain:a", "terrain:a")
    elif corruption == "untyped_attribution":
        parameters["destruction_attribution"] = object()
    elif corruption == "untyped_witness":
        parameters["source_rules_unit_objective_proximity_witness"] = object()
    elif corruption == "battle_round":
        parameters["battle_round"] = 0
    else:
        raise AssertionError(f"unsupported destruction evidence corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        PrimaryUnitDestructionEvidence(**parameters)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("turn_order_not_tuple", "turn_order must be a tuple"),
        ("turn_order_duplicate", "turn_order must not contain duplicates"),
        ("turn_order_short", "turn_order must contain at least 2 values"),
        ("active_unknown", "active player is not in turn_order"),
        ("scorer_unknown", "scoring player is not in turn_order"),
        ("scorer_not_active", "scoring player must be the active player"),
        ("evidence_not_tuple", "Primary destruction evidence must be a tuple"),
        ("evidence_untyped", "must contain typed evidence rows"),
        ("evidence_duplicate", "must not duplicate destruction occurrences"),
        ("evidence_unknown_player", "destruction player is not in turn_order"),
        ("no_previous_turn", "Previous player turn does not exist"),
    ],
)
def test_cross_turn_destruction_comparison_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    evidence = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:comparison",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="unit:destroyed",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    turn_order: object = ("player-a", "player-b")
    battle_round = 2
    active_player_id = "player-a"
    scoring_player_id = "player-a"
    rows: object = (evidence,)
    if corruption == "turn_order_not_tuple":
        turn_order = ["player-a", "player-b"]
    elif corruption == "turn_order_duplicate":
        turn_order = ("player-a", "player-a")
    elif corruption == "turn_order_short":
        turn_order = ("player-a",)
    elif corruption == "active_unknown":
        active_player_id = "player-c"
    elif corruption == "scorer_unknown":
        scoring_player_id = "player-c"
    elif corruption == "scorer_not_active":
        scoring_player_id = "player-b"
    elif corruption == "evidence_not_tuple":
        rows = [evidence]
    elif corruption == "evidence_untyped":
        rows = (object(),)
    elif corruption == "evidence_duplicate":
        rows = (evidence, evidence)
    elif corruption == "evidence_unknown_player":
        rows = (replace(evidence, destroyed_player_id="player-c"),)
    elif corruption == "no_previous_turn":
        battle_round = 1
    else:
        raise AssertionError(f"unsupported cross-turn corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        cross_turn_destruction_comparison_evidence(
            turn_order=cast(tuple[str, ...], turn_order),
            battle_round=battle_round,
            active_player_id=active_player_id,
            scoring_player_id=scoring_player_id,
            destruction_evidence=cast(tuple[PrimaryUnitDestructionEvidence, ...], rows),
        )


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    [
        ("negative_score", "score_count must be a non-negative integer"),
        ("opponent_setup", "Opponent-home scoring requires MissionSetup"),
        ("opponent_player", "Opponent-home scoring player is not in MissionSetup"),
        ("home_setup", "Home objective lookup requires MissionSetup"),
        ("home_player", "Home objective player is not in MissionSetup"),
    ],
)
def test_primary_scoring_condition_input_validation_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    operation: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_invalid_primary_scoring_operation(
            mission_setup=battlefield_dominance_setup,
            operation=operation,
        )


def _run_invalid_primary_scoring_operation(
    *,
    mission_setup: MissionSetup,
    operation: str,
) -> object:
    if operation == "negative_score":
        return primary_score_count_evidence(score_count=-1)
    if operation == "opponent_setup":
        return opponent_home_control_evidence(
            mission_setup=cast(MissionSetup, object()),
            player_id="player-a",
            controlled_objective_ids=(),
        )
    if operation == "opponent_player":
        return opponent_home_control_evidence(
            mission_setup=mission_setup,
            player_id="player-c",
            controlled_objective_ids=(),
        )
    if operation == "home_setup":
        return home_objective_ids(cast(MissionSetup, object()), player_id="player-a")
    if operation == "home_player":
        return home_objective_ids(mission_setup, player_id="player-c")
    raise AssertionError(f"unsupported Primary scoring validation operation: {operation}")


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("record", "requires an ObjectiveControlRecord"),
        ("mission_setup", "requires MissionSetup"),
        ("turn_order_not_tuple", "turn_order must be a tuple"),
        ("turn_order_duplicate", "turn_order must not contain duplicates"),
        ("turn_order_count", "turn_order must contain exactly two players"),
        ("turn_order_setup", "turn_order must match MissionSetup players"),
        ("player", "player is missing from turn_order"),
        ("active_player", "active player is missing from turn_order"),
        ("end_of_battle", "end_of_battle must be a bool"),
        ("inactive_player", "must evaluate for the active player"),
        ("destruction_not_tuple", "destruction evidence must be a tuple"),
        ("destruction_untyped", "destruction evidence must contain typed rows"),
        ("destruction_duplicate", "must not duplicate occurrences"),
        ("destruction_player", "destruction evidence references an unknown player"),
        ("destruction_future", "cannot come from a future battle round"),
        ("spatial_untyped", "spatial evidence must be typed evidence"),
        ("spatial_player", "spatial evidence belongs to another player"),
        ("turn_start_objective", "turn-start evidence references an unknown objective"),
        ("destruction_objective", "destruction evidence references an unknown objective"),
        ("control_player", "objective control references an unknown controlling player"),
        ("score_player", "objective control score references an unknown player"),
        ("contribution_player", "objective contribution references an unknown player"),
    ],
)
def test_primary_scoring_condition_context_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_scoring_context_corruption(
            mission_setup=battlefield_dominance_setup,
            corruption=corruption,
        )


def _run_primary_scoring_context_corruption(
    *,
    mission_setup: MissionSetup,
    corruption: str,
) -> None:
    typed_record = _control_record(mission_setup, battle_round=2)
    evidence = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:context-validation",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="unit:context-validation",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    parameters: dict[str, Any] = {
        "record": typed_record,
        "mission_setup": mission_setup,
        "turn_order": ("player-a", "player-b"),
        "player_id": "player-a",
        "turn_start_controlled_objective_ids": None,
        "destruction_evidence": (),
        "spatial_evidence": None,
        "end_of_battle": False,
    }
    if corruption == "record":
        parameters["record"] = object()
    elif corruption == "mission_setup":
        parameters["mission_setup"] = object()
    elif corruption == "turn_order_not_tuple":
        parameters["turn_order"] = ["player-a", "player-b"]
    elif corruption == "turn_order_duplicate":
        parameters["turn_order"] = ("player-a", "player-a")
    elif corruption == "turn_order_count":
        parameters["turn_order"] = ("player-a",)
    elif corruption == "turn_order_setup":
        parameters["turn_order"] = ("player-a", "player-c")
    elif corruption == "player":
        parameters["player_id"] = "player-c"
    elif corruption == "active_player":
        parameters["record"] = replace(typed_record, active_player_id="player-c")
    elif corruption == "end_of_battle":
        parameters["end_of_battle"] = 1
    elif corruption == "inactive_player":
        parameters["player_id"] = "player-b"
    elif corruption == "destruction_not_tuple":
        parameters["destruction_evidence"] = [evidence]
    elif corruption == "destruction_untyped":
        parameters["destruction_evidence"] = (object(),)
    elif corruption == "destruction_duplicate":
        parameters["destruction_evidence"] = (evidence, evidence)
    elif corruption == "destruction_player":
        parameters["destruction_evidence"] = (replace(evidence, destroyed_player_id="player-c"),)
    elif corruption == "destruction_future":
        parameters["destruction_evidence"] = (replace(evidence, battle_round=3),)
    elif corruption == "spatial_untyped":
        parameters["spatial_evidence"] = object()
    elif corruption == "spatial_player":
        parameters["spatial_evidence"] = replace(
            _spatial_evidence(
                record=typed_record,
                opponent_territory_ids=_territory_objective_ids(
                    mission_setup,
                    owner_role="defender",
                ),
            ),
            player_id="player-b",
        )
    elif corruption == "turn_start_objective":
        parameters["turn_start_controlled_objective_ids"] = ("objective:forged",)
    elif corruption == "destruction_objective":
        parameters["destruction_evidence"] = (
            replace(evidence, started_turn_objective_marker_ids=("objective:forged",)),
        )
    elif corruption in {"control_player", "score_player", "contribution_player"}:
        result = typed_record.results[0]
        if corruption == "control_player":
            result = replace(
                result,
                status=ObjectiveControlStatus.CONTROLLED,
                controlled_by_player_id="player-c",
                scores=(ObjectiveControlScore(player_id="player-c", score=1),),
            )
        elif corruption == "score_player":
            result = replace(
                result,
                status=ObjectiveControlStatus.CONTROLLED,
                controlled_by_player_id="player-a",
                scores=(
                    ObjectiveControlScore(player_id="player-a", score=1),
                    ObjectiveControlScore(player_id="player-c", score=0),
                ),
            )
        else:
            result = replace(
                result,
                contributors=(
                    ObjectiveControlContribution(
                        player_id="player-c",
                        unit_instance_id="unit:forged",
                        model_instance_id="model:forged",
                        objective_control=1,
                        effective_objective_control=1,
                        battle_shocked=False,
                        horizontal_distance_inches=0.0,
                        vertical_gap_inches=0.0,
                    ),
                ),
            )
        parameters["record"] = replace(
            typed_record,
            results=(result, *typed_record.results[1:]),
        )
    else:
        raise AssertionError(f"unsupported Primary scoring context corruption: {corruption}")
    PrimaryScoringConditionContext(**parameters)


def test_primary_scoring_condition_evaluation_fails_closed_on_typed_context_drift(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    record = _control_record(battlefield_dominance_setup, battle_round=2)
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=battlefield_dominance_setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="requires a typed context"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective",
            context=cast(PrimaryScoringConditionContext, object()),
        )
    no_territory_setup = replace(
        battlefield_dominance_setup,
        battlefield_regions=tuple(
            region
            for region in battlefield_dominance_setup.battlefield_regions
            if region.region_kind is not BattlefieldRegionKind.TERRITORY
        ),
    )
    no_territory_context = replace(context, mission_setup=no_territory_setup)
    with pytest.raises(GameLifecycleError, match="exactly one directed territory"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective_in_opponent_territory",
            context=replace(
                no_territory_context,
                spatial_evidence=_spatial_evidence(
                    record=record,
                    opponent_territory_ids=(),
                ),
            ),
        )
    spatial = _spatial_evidence(
        record=record,
        opponent_territory_ids=("objective:forged",),
    )
    with pytest.raises(GameLifecycleError, match="opponent-territory objectives drifted"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective_in_opponent_territory",
            context=replace(context, spatial_evidence=spatial),
        )


def test_primary_scoring_condition_direct_count_and_same_round_previous_turn(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    mission_setup = battlefield_dominance_setup
    controlled_id = mission_setup.objective_markers[0].objective_marker_id
    record = _control_record(
        mission_setup,
        battle_round=2,
        controlled_by_a=(controlled_id,),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=mission_setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )

    assert (
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective",
            context=context,
        )["score_count"]
        == 1
    )
    comparison = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-b",
        scoring_player_id="player-b",
        destruction_evidence=(),
    )
    assert comparison["previous_turn_battle_round"] == 2
    assert comparison["previous_turn_active_player_id"] == "player-a"


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("event_log", "Primary historical evidence requires EventLog"),
        ("objective_state", "Primary turn-start event requires typed objective evidence"),
        ("position_snapshot", "Primary turn-start event requires a typed position snapshot"),
        (
            "game_id",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
        (
            "active_player_id",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
        (
            "battle_round",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
    ],
)
def test_primary_turn_start_historical_event_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    objective_state, position_snapshot, _destruction = _primary_historical_evidence_fixture(
        battlefield_dominance_setup
    )
    event_log = EventLog()
    if corruption == "event_log":
        event_log = cast(EventLog, object())
    elif corruption == "objective_state":
        objective_state = cast(PrimaryObjectiveTurnStartState, object())
    elif corruption == "position_snapshot":
        position_snapshot = cast(PrimaryRulesUnitTurnStartSnapshot, object())
    elif corruption == "game_id":
        position_snapshot = replace(position_snapshot, game_id="game:drifted")
    elif corruption == "active_player_id":
        position_snapshot = replace(position_snapshot, active_player_id="player-b")
    elif corruption == "battle_round":
        position_snapshot = replace(position_snapshot, battle_round=3)
    else:
        raise AssertionError(f"unsupported historical-event corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        record_primary_turn_start_evidence_event(
            event_log=event_log,
            objective_state=objective_state,
            position_snapshot=position_snapshot,
        )


def test_primary_historical_events_record_exact_typed_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    objective_state, position_snapshot, destruction = _primary_historical_evidence_fixture(
        battlefield_dominance_setup
    )
    event_log = EventLog()

    turn_start_record = record_primary_turn_start_evidence_event(
        event_log=event_log,
        objective_state=objective_state,
        position_snapshot=position_snapshot,
    )
    destruction_record = record_primary_unit_destruction_event(
        event_log=event_log,
        destruction=destruction,
    )
    turn_start_payload = cast(dict[str, JsonValue], turn_start_record.payload)
    destruction_payload = cast(dict[str, JsonValue], destruction_record.payload)

    assert turn_start_record.event_type == PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT
    assert turn_start_payload["primary_objective_turn_start_state"] == objective_state.to_payload()
    assert destruction_record.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
    assert destruction_payload["primary_unit_destruction_state"] == destruction.to_payload()

    with pytest.raises(
        GameLifecycleError,
        match="Primary unit destruction event requires typed destruction evidence",
    ):
        record_primary_unit_destruction_event(
            event_log=event_log,
            destruction=cast(PrimaryUnitDestructionState, object()),
        )


@pytest.mark.parametrize(
    ("cap_audit", "expected_error"),
    [
        ("invalid", "Primary VP transaction cap audit must be an object"),
        (
            {"requested_amount": 0, "applied_amount": 9},
            "Primary VP transaction cap audit requires positive requested_amount",
        ),
        (
            {"requested_amount": 9, "applied_amount": 8},
            "Primary VP transaction cap audit applied_amount drifted",
        ),
        (
            {"requested_amount": 8, "applied_amount": 9},
            "Primary VP transaction cap audit applied_amount exceeds requested_amount",
        ),
    ],
)
def test_primary_victory_point_transaction_cap_audit_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    cap_audit: object,
    expected_error: str,
) -> None:
    policy, boundary, award = _primary_vp_policy_fixture(battlefield_dominance_setup)
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    metadata["vp_cap_audit"] = cast(JsonValue, cap_audit)
    transaction = _primary_transaction_from_award(award=award, metadata=metadata)

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_victory_point_transaction(
            policy=policy,
            transaction=transaction,
            objective_control_records=(boundary,),
            turn_order=("player-a", "player-b"),
        )


def test_primary_victory_point_transaction_validates_cap_audit_and_ledger_uniqueness(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    policy, boundary, award = _primary_vp_policy_fixture(battlefield_dominance_setup)
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    metadata["vp_cap_audit"] = {
        "requested_amount": award.amount,
        "applied_amount": award.amount,
    }
    transaction = _primary_transaction_from_award(award=award, metadata=metadata)

    assert (
        validate_primary_victory_point_transaction(
            policy=policy,
            transaction=transaction,
            objective_control_records=(boundary,),
            turn_order=("player-a", "player-b"),
        ).scoring_rule_id
        == cast(dict[str, object], award.metadata)["scoring_rule_id"]
    )

    with pytest.raises(GameLifecycleError, match="VP ledger and policy player_id drift"):
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=VictoryPointLedger.initial(player_id="player-b"),
            objective_control_records=(boundary,),
            turn_order=("player-a", "player-b"),
        )

    duplicate = replace(transaction, transaction_id="victory-point:player-a:round-02:000002")
    ledger = VictoryPointLedger(
        player_id="player-a",
        victory_points=transaction.amount + duplicate.amount,
        transactions=(transaction, duplicate),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Primary VP ledger must not repeat a scoring rule at one boundary",
    ):
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=ledger,
            objective_control_records=(boundary,),
            turn_order=("player-a", "player-b"),
        )


def test_end_of_battle_territory_condition_is_spatial_and_fail_closed(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    record = _control_record(setup, battle_round=5)
    clear_context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        spatial_evidence=_spatial_evidence(
            record=record,
            opponent_territory_ids=_territory_objective_ids(
                setup,
                owner_role="defender",
            ),
        ),
        end_of_battle=True,
    )
    blocked_spatial = replace(
        cast(PrimaryScoringSpatialEvidence, clear_context.spatial_evidence),
        enemy_units_wholly_within_own_territory=(
            PrimaryTerritoryUnitWitness(
                rules_unit_instance_id="enemy-rules-unit:one",
                model_instance_ids=("enemy-model:one",),
            ),
        ),
    )

    clear = evaluate_primary_scoring_condition(
        condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
        context=clear_context,
    )
    blocked = evaluate_primary_scoring_condition(
        condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
        context=replace(clear_context, spatial_evidence=blocked_spatial),
    )

    assert clear["score_count"] == 1
    assert blocked["score_count"] == 0
    assert blocked["enemy_unit_instance_ids"] == ["enemy-rules-unit:one"]
    with pytest.raises(GameLifecycleError, match="requires spatial evidence"):
        evaluate_primary_scoring_condition(
            condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
            context=replace(clear_context, spatial_evidence=None),
        )


def test_condition_named_time_windows_fail_closed_outside_their_window(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    defender_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("defender-home")
    )
    non_home_ids = tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id != attacker_home_id
    )
    controlled_ids = (attacker_home_id, *non_home_ids)

    def context_for_round(battle_round: int) -> PrimaryScoringConditionContext:
        record = _control_record(
            setup,
            battle_round=battle_round,
            controlled_by_a=controlled_ids,
        )
        return PrimaryScoringConditionContext(
            record=record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
            spatial_evidence=_spatial_evidence(
                record=record,
                opponent_territory_ids=_territory_objective_ids(
                    setup,
                    owner_role="defender",
                ),
            ),
        )

    outside_window_cases = (
        ("each_non_home_objective_controlled_round_five", context_for_round(4)),
        (
            "control_more_objectives_than_opponent_first_and_second_battle_round",
            context_for_round(3),
        ),
        (
            "control_more_objectives_than_opponent_from_battle_round_two",
            context_for_round(1),
        ),
        ("control_two_or_more_objectives_from_battle_round_two", context_for_round(1)),
        ("each_non_home_objective_controlled_first_battle_round", context_for_round(2)),
        (
            "each_non_home_objective_controlled_battle_rounds_two_and_three",
            context_for_round(4),
        ),
        (
            "each_non_home_objective_controlled_battle_round_four_onwards",
            context_for_round(3),
        ),
        ("control_opponent_home_objective_end_of_battle", context_for_round(5)),
        (
            "no_enemy_units_wholly_within_own_territory_end_of_battle",
            context_for_round(5),
        ),
    )
    assert defender_home_id in controlled_ids
    for condition, context in outside_window_cases:
        evidence = evaluate_primary_scoring_condition(
            condition=condition,
            context=context,
        )
        assert evidence["score_count"] == 0, condition


def test_primary_condition_context_rejects_partial_or_drifted_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    exact_record = _control_record(setup, battle_round=2)
    partial_record = replace(exact_record, results=exact_record.results[:-1])

    with pytest.raises(GameLifecycleError, match="exactly the MissionSetup objectives"):
        PrimaryScoringConditionContext(
            record=partial_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
        )
    unsupported_result = ObjectiveControlResult.unsupported(
        objective_id=exact_record.results[0].objective_id,
        unsupported_reason="unsupported:test",
    )
    with pytest.raises(GameLifecycleError, match="unsupported objective-control"):
        PrimaryScoringConditionContext(
            record=replace(
                exact_record,
                results=(unsupported_result, *exact_record.results[1:]),
            ),
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
        )
    context = PrimaryScoringConditionContext(
        record=exact_record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )
    spatial = _spatial_evidence(
        record=exact_record,
        opponent_territory_ids=_territory_objective_ids(
            setup,
            owner_role="defender",
        ),
    )
    with pytest.raises(GameLifecycleError, match="spatial evidence context drift"):
        PrimaryScoringConditionContext(
            record=replace(
                exact_record,
                record_id="phase17n-primary-control-record:stale",
            ),
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
            spatial_evidence=spatial,
        )
    under_provisioned = replace(
        spatial,
        requested_condition_ids=("each_controlled_objective_in_opponent_territory",),
        table_quarter_unit_witnesses=(),
        enemy_units_wholly_within_own_territory=(),
    )
    with pytest.raises(GameLifecycleError, match="was not provisioned"):
        evaluate_primary_scoring_condition(
            condition=(
                "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
                "not_within_six_of_center"
            ),
            context=PrimaryScoringConditionContext(
                record=exact_record,
                mission_setup=setup,
                turn_order=("player-a", "player-b"),
                player_id="player-a",
                spatial_evidence=under_provisioned,
            ),
        )
    with pytest.raises(GameLifecycleError, match="turn-start objective snapshot"):
        evaluate_primary_scoring_condition(
            condition="each_newly_controlled_non_home_objective_this_turn",
            context=context,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring condition"):
        evaluate_primary_scoring_condition(
            condition="source_text_guess",
            context=context,
        )


def _primary_vp_policy_fixture(
    mission_setup: MissionSetup,
) -> tuple[MissionScoringPolicy, ObjectiveControlRecord, VictoryPointAward]:
    controlled_by_a = tuple(
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if marker.objective_marker_id.endswith(("attacker-home", "central", "east"))
    )
    boundary = _control_record(
        mission_setup,
        battle_round=2,
        controlled_by_a=controlled_by_a,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )
    boundary = replace(
        boundary,
        record_id=(
            f"objective-control:round-{boundary.battle_round:02d}:"
            f"{boundary.active_player_id}:{boundary.phase}:{boundary.timing.value}"
        ),
    )
    policies = mission_scoring_policies_from_setup(mission_setup)
    policy = policies.policy_for_player("player-a")
    award = next(
        candidate
        for candidate in policies.primary_awards_from_objective_control(
            record=boundary,
            mission_setup=mission_setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
        if cast(dict[str, object], candidate.metadata)["scoring_rule_id"]
        == "battlefield-dominance-each-objective"
    )
    binding = validate_primary_victory_point_award(
        policy=policy,
        award=award,
        objective_control_records=(boundary,),
        turn_order=("player-a", "player-b"),
        expected_boundary_active_player_id="player-a",
    )
    assert binding.scoring_rule_id == "battlefield-dominance-each-objective"
    return policy, boundary, award


def _primary_transaction_from_award(
    *,
    award: VictoryPointAward,
    metadata: JsonValue,
) -> VictoryPointTransaction:
    _ledger, transaction = VictoryPointLedger.initial(player_id=award.player_id).award(
        award,
        metadata=metadata,
    )
    return transaction


def _primary_historical_evidence_fixture(
    mission_setup: MissionSetup,
) -> tuple[
    PrimaryObjectiveTurnStartState,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryUnitDestructionState,
]:
    objective_record = _control_record(
        mission_setup,
        battle_round=2,
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND,
    )
    objective_state = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:historical-player-a:round-2",
        game_id=objective_record.game_id,
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=objective_record,
        controlled_objective_ids=(),
        source_id="source:primary-turn-start:historical-player-a:round-2",
    )
    position_snapshot = PrimaryRulesUnitTurnStartSnapshot(
        snapshot_id="primary-position:historical-player-a:round-2",
        game_id=objective_record.game_id,
        active_player_id="player-a",
        battle_round=2,
        rules_unit_memberships=(),
        source_id="source:primary-position:historical-player-a:round-2",
    )
    destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:historical-coherency",
        game_id=objective_record.game_id,
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=("primary-departure:historical-coherency",),
        unattributed_cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
        source_mutation_id="end-turn-cleanup:historical-coherency",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.COMMAND.value,
        destroyed_unit_instance_id="enemy-unit:historical-coherency",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
        source_id="source:primary-destruction:historical-coherency",
    )
    return objective_state, position_snapshot, destruction


def _control_record(
    mission_setup: MissionSetup,
    *,
    battle_round: int,
    controlled_by_a: tuple[str, ...] = (),
    controlled_by_b: tuple[str, ...] = (),
    timing: ObjectiveControlTiming = ObjectiveControlTiming.TURN_END,
    phase: BattlePhase = BattlePhase.FIGHT,
) -> ObjectiveControlRecord:
    controlled_by_a_set = set(controlled_by_a)
    controlled_by_b_set = set(controlled_by_b)
    if controlled_by_a_set.intersection(controlled_by_b_set):
        raise AssertionError("test objective cannot be controlled by both players")
    results: list[ObjectiveControlResult] = []
    for marker in mission_setup.objective_markers:
        if marker.objective_marker_id in controlled_by_a_set:
            results.append(_controlled_result(marker.objective_marker_id, "player-a"))
        elif marker.objective_marker_id in controlled_by_b_set:
            results.append(_controlled_result(marker.objective_marker_id, "player-b"))
        else:
            results.append(
                ObjectiveControlResult(
                    objective_id=marker.objective_marker_id,
                    status=ObjectiveControlStatus.UNCONTROLLED,
                    controlled_by_player_id=None,
                    scores=(),
                )
            )
    return ObjectiveControlRecord(
        record_id=f"phase17n-primary-control-record:{battle_round}",
        game_id="phase17n-primary-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=timing,
        phase=phase.value,
        battlefield_id="phase17n-primary-battlefield",
        results=tuple(results),
    )


def _controlled_result(objective_id: str, player_id: str) -> ObjectiveControlResult:
    return ObjectiveControlResult(
        objective_id=objective_id,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id=player_id,
        scores=(ObjectiveControlScore(player_id=player_id, score=1),),
    )


def _territory_objective_ids(
    mission_setup: MissionSetup,
    *,
    owner_role: str,
) -> tuple[str, ...]:
    territory = next(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == owner_role
    )
    return tuple(
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if territory.contains_point(marker.x_inches, marker.y_inches)
    )


def _spatial_evidence(
    *,
    record: ObjectiveControlRecord,
    opponent_territory_ids: tuple[str, ...],
) -> PrimaryScoringSpatialEvidence:
    return PrimaryScoringSpatialEvidence(
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        player_id="player-a",
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        table_quarter_unit_witnesses=tuple(
            sorted(
                (
                    PrimaryTableQuarterUnitWitness(
                        rules_unit_instance_id=f"friendly-rules-unit:{index}",
                        quarter_id=quarter_id,
                        model_instance_ids=(f"friendly-model:{index}",),
                    )
                    for index, quarter_id in enumerate(TABLE_QUARTER_IDS, start=1)
                ),
                key=lambda witness: (
                    witness.quarter_id,
                    witness.rules_unit_instance_id,
                ),
            )
        ),
        enemy_units_wholly_within_own_territory=(),
        opponent_territory_objective_ids=opponent_territory_ids,
    )
