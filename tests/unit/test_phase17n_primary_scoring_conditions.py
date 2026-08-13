from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    TABLE_QUARTER_IDS,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    objective_control_record_hash,
)
from warhammer40k_core.engine.scoring import (
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
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
        destroying_player_id="player-a",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        destroyed_unit_instance_id="enemy-unit:foreign",
        started_turn_terrain_feature_ids=(),
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
                    destroying_player_id="player-unknown",
                ),
            ),
        )


def test_exact_twelve_implemented_primaries_build_typed_runtime_rules() -> None:
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
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:one",
            started_turn_terrain_feature_ids=("terrain-area:alpha",),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:enemy-two",
            battle_round=2,
            active_player_id="player-a",
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:two",
            started_turn_terrain_feature_ids=(),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:friendly-previous",
            battle_round=1,
            active_player_id="player-b",
            destroyed_player_id="player-a",
            destroyed_unit_instance_id="friendly-unit:previous",
            started_turn_terrain_feature_ids=(),
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
