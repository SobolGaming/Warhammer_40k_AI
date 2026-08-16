from __future__ import annotations

from tests.phase17n_primary_mission_helpers import phase17n_event_setup

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)


def test_phase17n_step5a_first_round_central_objective_condition_is_windowed() -> None:
    setup = _setup()
    central_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.CENTRAL)[0]
    expansion_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.EXPANSION)[0]

    achieved = evaluate_primary_scoring_condition(
        condition="control_one_or_more_central_objectives_first_battle_round",
        context=_context(setup=setup, battle_round=1, controlled_objective_ids=(central_id,)),
    )
    outside_window = evaluate_primary_scoring_condition(
        condition="control_one_or_more_central_objectives_first_battle_round",
        context=_context(setup=setup, battle_round=2, controlled_objective_ids=(central_id,)),
    )
    non_central = evaluate_primary_scoring_condition(
        condition="control_one_or_more_central_objectives_first_battle_round",
        context=_context(setup=setup, battle_round=1, controlled_objective_ids=(expansion_id,)),
    )

    assert achieved == _expected_evidence(score_count=1, controlled_objective_ids=(central_id,))
    assert outside_window == _expected_evidence(score_count=0)
    assert non_central == _expected_evidence(score_count=0)


def test_phase17n_step5a_three_objective_condition_starts_in_round_two() -> None:
    setup = _setup()
    controlled_ids = tuple(marker.objective_marker_id for marker in setup.objective_markers[:3])

    achieved = evaluate_primary_scoring_condition(
        condition="control_three_or_more_objectives_from_battle_round_two",
        context=_context(setup=setup, battle_round=2, controlled_objective_ids=controlled_ids),
    )
    outside_window = evaluate_primary_scoring_condition(
        condition="control_three_or_more_objectives_from_battle_round_two",
        context=_context(setup=setup, battle_round=1, controlled_objective_ids=controlled_ids),
    )
    below_threshold_ids = controlled_ids[:2]
    below_threshold = evaluate_primary_scoring_condition(
        condition="control_three_or_more_objectives_from_battle_round_two",
        context=_context(
            setup=setup,
            battle_round=2,
            controlled_objective_ids=below_threshold_ids,
        ),
    )

    assert achieved == _expected_evidence(
        score_count=1,
        controlled_objective_ids=controlled_ids,
        objective_count_threshold=3,
    )
    assert outside_window == _expected_evidence(score_count=0, objective_count_threshold=3)
    assert below_threshold == _expected_evidence(
        score_count=0,
        controlled_objective_ids=below_threshold_ids,
        objective_count_threshold=3,
    )


def test_phase17n_step5a_four_objective_condition_requires_end_of_battle() -> None:
    setup = _setup()
    controlled_ids = tuple(marker.objective_marker_id for marker in setup.objective_markers[:4])

    achieved = evaluate_primary_scoring_condition(
        condition="control_four_or_more_objectives_end_of_battle",
        context=_context(
            setup=setup,
            battle_round=5,
            controlled_objective_ids=controlled_ids,
            end_of_battle=True,
        ),
    )
    ordinary_turn_end = evaluate_primary_scoring_condition(
        condition="control_four_or_more_objectives_end_of_battle",
        context=_context(
            setup=setup,
            battle_round=5,
            controlled_objective_ids=controlled_ids,
            end_of_battle=False,
        ),
    )
    below_threshold_ids = controlled_ids[:3]
    below_threshold = evaluate_primary_scoring_condition(
        condition="control_four_or_more_objectives_end_of_battle",
        context=_context(
            setup=setup,
            battle_round=5,
            controlled_objective_ids=below_threshold_ids,
            end_of_battle=True,
        ),
    )

    assert achieved == _expected_evidence(
        score_count=1,
        controlled_objective_ids=controlled_ids,
        objective_count_threshold=4,
    )
    assert ordinary_turn_end == _expected_evidence(score_count=0, objective_count_threshold=4)
    assert below_threshold == _expected_evidence(
        score_count=0,
        controlled_objective_ids=below_threshold_ids,
        objective_count_threshold=4,
    )


def test_phase17n_step5a_controlled_non_home_central_condition_is_exact() -> None:
    setup = _setup()
    central_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.CENTRAL)[0]
    expansion_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.EXPANSION)[0]
    home_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.ATTACKER_HOME)[0]
    opponent_home_id = _objective_ids_for_role(setup, ObjectiveMarkerRole.DEFENDER_HOME)[0]

    achieved = evaluate_primary_scoring_condition(
        condition="one_or_more_controlled_non_home_objectives_is_central_objective",
        context=_context(
            setup=setup,
            battle_round=2,
            controlled_objective_ids=(home_id, central_id, opponent_home_id),
        ),
    )
    no_central_objective = evaluate_primary_scoring_condition(
        condition="one_or_more_controlled_non_home_objectives_is_central_objective",
        context=_context(
            setup=setup,
            battle_round=2,
            controlled_objective_ids=(home_id, expansion_id, opponent_home_id),
        ),
    )

    assert achieved == _expected_evidence(
        score_count=1,
        controlled_objective_ids=(central_id,),
        home_objective_ids=(home_id,),
    )
    assert no_central_objective == _expected_evidence(
        score_count=0,
        home_objective_ids=(home_id,),
    )


def _setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="reconnaissance-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="reconnaissance",
    )


def _objective_ids_for_role(
    setup: MissionSetup,
    role: ObjectiveMarkerRole,
) -> tuple[str, ...]:
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is role
    )


def _context(
    *,
    setup: MissionSetup,
    battle_round: int,
    controlled_objective_ids: tuple[str, ...],
    end_of_battle: bool = False,
) -> PrimaryScoringConditionContext:
    controlled_ids = set(controlled_objective_ids)
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(
                (
                    ObjectiveControlContribution(
                        player_id="player-a",
                        unit_instance_id=f"unit-{index:02d}",
                        model_instance_id=f"model-{index:02d}",
                        objective_control=1,
                        effective_objective_control=1,
                        battle_shocked=False,
                        horizontal_distance_inches=0.0,
                        vertical_gap_inches=0.0,
                    ),
                )
                if marker.objective_marker_id in controlled_ids
                else ()
            ),
        )
        for index, marker in enumerate(setup.objective_markers, start=1)
    )
    record = ObjectiveControlRecord(
        record_id=f"step5a-objective-record-round-{battle_round}",
        game_id="step5a-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5a-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        end_of_battle=end_of_battle,
    )


def _expected_evidence(
    *,
    score_count: int,
    controlled_objective_ids: tuple[str, ...] = (),
    home_objective_ids: tuple[str, ...] = (),
    objective_count_threshold: int | None = None,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "score_count": score_count,
        "controlled_objective_ids": sorted(controlled_objective_ids),
        "home_objective_ids": sorted(home_objective_ids),
        "turn_start_controlled_objective_ids": [],
        "trapped_terrain_feature_ids": [],
        "destroyed_unit_instance_ids": [],
    }
    if objective_count_threshold is not None:
        evidence["objective_count_threshold"] = objective_count_threshold
    return evidence
