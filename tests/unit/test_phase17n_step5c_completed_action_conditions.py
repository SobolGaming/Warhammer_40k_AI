from __future__ import annotations

from dataclasses import replace

import pytest
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
)

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import primary_scoring_rules_from_definition
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_scoring_action_conditions import (
    COMMIT_SABOTAGE_ACTION_ID,
    EXTRACT_INTELLIGENCE_ACTION_ID,
    PRIMARY_SCORING_ACTION_CONDITIONS,
    SECURE_ASSET_ACTION_ID,
    SENSOR_SWEEP_EXTRACT_ACTION_ID,
    VANGUARD_OPERATION_ACTION_ID,
    evaluate_action_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SABOTAGE_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_step5c_action_conditions_are_registered() -> None:
    assert PRIMARY_SCORING_ACTION_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert (
        PRIMARY_SCORING_SABOTAGE_OPPONENT_TERRITORY_OBJECTIVE_CONDITION
        in PRIMARY_SCORING_SPATIAL_CONDITIONS
    )


def test_phase17n_step5c_promotes_completed_action_primary_missions() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    for mission_id in (
        "primary-sabotage",
        "primary-secure-asset",
        "primary-vanguard-operation",
    ):
        rules = primary_scoring_rules_from_definition(primary_by_id[mission_id])
        assert rules
        assert all(rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS for rule in rules)


def test_phase17n_step5c_keeps_remaining_condition_pending_missions_fail_closed() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    for mission_id in (
        "primary-gather-intel",
        "primary-extract-relic",
        "primary-surveil-the-foe",
        "primary-locate-and-deny",
        "primary-vital-link",
    ):
        assert (
            primary_scoring_rules_from_definition(
                primary_by_id[mission_id],
                require_supported=False,
            )
            == ()
        )
        with pytest.raises(
            GameLifecycleError,
            match="source is known but engine implementation is pending",
        ):
            primary_scoring_rules_from_definition(primary_by_id[mission_id])


def test_phase17n_step5c_action_conditions_require_state_evidence() -> None:
    setup = _sabotage_setup()
    context = _objective_context(setup=setup, battle_round=1)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition="each_friendly_unit_committed_sabotage_this_turn",
            context=context,
        )


def test_phase17n_step5c_counts_unique_completed_units_and_ignores_other_actions() -> None:
    setup = _sabotage_setup()
    objective_ids = _non_home_objective_ids(setup)
    matching = evaluate_action_scoring_condition(
        condition_id="each_friendly_unit_committed_sabotage_this_turn",
        actions=(
            _completed_action(
                setup,
                mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-1",
                target_id=objective_ids[0],
                action_index=1,
            ),
            _completed_action(
                setup,
                mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-1",
                target_id=objective_ids[1],
                action_index=2,
            ),
            _completed_action(
                setup,
                mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-2",
                target_id=objective_ids[2],
                action_index=3,
            ),
            _completed_action(
                setup,
                mission_action_id=SECURE_ASSET_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-3",
                target_id=objective_ids[0],
                action_index=4,
                mission_id="primary-secure-asset",
            ),
            _interrupted_action(
                setup,
                mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-4",
                target_id=objective_ids[0],
                action_index=5,
            ),
            _completed_action(
                setup,
                mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                unit_instance_id="army-alpha:intercessor-unit-5",
                target_id=objective_ids[0],
                action_index=6,
                battle_round=2,
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
    )
    assert matching["score_count"] == 2
    assert matching["completed_unit_instance_ids"] == [
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    ]


def test_phase17n_step5c_rejects_duplicate_action_ids() -> None:
    setup = _sabotage_setup()
    action = _completed_action(
        setup,
        mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=_non_home_objective_ids(setup)[0],
    )
    with pytest.raises(GameLifecycleError, match="must not duplicate action_id"):
        evaluate_action_scoring_condition(
            condition_id="each_friendly_unit_committed_sabotage_this_turn",
            actions=(action, action),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5c_rejects_unknown_objective_targets() -> None:
    setup = _sabotage_setup()
    with pytest.raises(GameLifecycleError, match="unknown target"):
        evaluate_action_scoring_condition(
            condition_id="each_friendly_unit_committed_sabotage_this_turn",
            actions=(
                _completed_action(
                    setup,
                    mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                    unit_instance_id="army-alpha:intercessor-unit-1",
                    target_id="missing-objective",
                ),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5c_rejects_completed_action_source_identity_drift() -> None:
    setup = _sabotage_setup()
    action = replace(
        _completed_action(
            setup,
            mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id=_non_home_objective_ids(setup)[0],
        ),
        scoring_source_id="forged-scoring-source",
    )
    with pytest.raises(GameLifecycleError, match="source identity drifted"):
        evaluate_action_scoring_condition(
            condition_id="each_friendly_unit_committed_sabotage_this_turn",
            actions=(action,),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5c_sensor_sweep_ignores_locate_and_deny_actions() -> None:
    setup = _extract_relic_setup()
    objective_id = _non_home_objective_ids(setup)[0]
    evidence = evaluate_action_scoring_condition(
        condition_id="friendly_unit_performed_sensor_sweep_this_turn",
        actions=(
            _completed_action(
                setup,
                mission_action_id="sensor-sweep-locate-and-deny",
                unit_instance_id="army-beta:intercessor-unit-1",
                target_id=objective_id,
                player_id="player-b",
            ),
            _completed_action(
                setup,
                mission_action_id=SENSOR_SWEEP_EXTRACT_ACTION_ID,
                unit_instance_id="army-beta:intercessor-unit-2",
                target_id=objective_id,
                player_id="player-b",
                action_index=2,
            ),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
    )
    assert evidence["score_count"] == 1
    assert evidence["completed_unit_instance_ids"] == ["army-beta:intercessor-unit-2"]


def test_phase17n_step5c_extract_intelligence_is_windowed_from_battle_round_two() -> None:
    setup = _gather_intel_setup()
    objective_id = _non_home_objective_ids(setup)[0]
    action = _completed_action(
        setup,
        mission_action_id=EXTRACT_INTELLIGENCE_ACTION_ID,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=objective_id,
        battle_round=1,
    )
    round_one = evaluate_action_scoring_condition(
        condition_id="each_friendly_unit_extracted_intelligence_this_turn",
        actions=(action,),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
    )
    round_two = evaluate_action_scoring_condition(
        condition_id="each_friendly_unit_extracted_intelligence_this_turn",
        actions=(replace(action, battle_round_started=2, completed_battle_round=2),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
    )
    assert round_one["score_count"] == 0
    assert round_two["score_count"] == 1


def test_phase17n_step5c_boolean_actions_score_once() -> None:
    setup = _secure_asset_setup()
    objective_id = _non_home_objective_ids(setup)[0]
    evidence = evaluate_action_scoring_condition(
        condition_id="friendly_unit_secured_asset_this_turn",
        actions=(
            _completed_action(
                setup,
                mission_action_id=SECURE_ASSET_ACTION_ID,
                unit_instance_id="army-beta:intercessor-unit-1",
                target_id=objective_id,
                player_id="player-b",
            ),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
    )
    assert evidence["score_count"] == 1
    empty = evaluate_action_scoring_condition(
        condition_id="friendly_unit_performed_sensor_sweep_this_turn",
        actions=(),
        mission_setup=_extract_relic_setup(),
        player_id="player-b",
        battle_round=1,
    )
    assert empty["score_count"] == 0


def test_phase17n_step5c_sabotage_territory_bonus_requires_spatial_evidence() -> None:
    setup = _sabotage_setup()
    with pytest.raises(GameLifecycleError, match="requires spatial evidence"):
        evaluate_action_scoring_condition(
            condition_id="each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn",
            actions=(
                _completed_action(
                    setup,
                    mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
                    unit_instance_id="army-alpha:intercessor-unit-1",
                    target_id=_non_home_objective_ids(setup)[0],
                ),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5c_scores_secure_asset_through_shared_boundary() -> None:
    state, record = _resolved_primary_action(
        layout_id="take-and-hold-vs-priority-assets-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id=SECURE_ASSET_ACTION_ID,
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-b")
    assert awards["friendly_unit_secured_asset_this_turn"] == 4
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()


def test_phase17n_step5c_scores_vanguard_through_shared_boundary() -> None:
    state, record = _resolved_primary_action(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id=VANGUARD_OPERATION_ACTION_ID,
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-b")
    assert awards["friendly_unit_performed_vanguard_operation_this_turn"] == 4
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()


def test_phase17n_step5c_failed_vanguard_does_not_score() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id=VANGUARD_OPERATION_ACTION_ID,
        current_phase=BattlePhase.FIGHT,
        vanguard_enemy_position="inside",
    )
    _bind_force_dispositions(state)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert resolved[0].status is MissionActionStatus.INTERRUPTED
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-b")
    assert "friendly_unit_performed_vanguard_operation_this_turn" not in awards
    assert action.target_id == target_id


def test_phase17n_step5c_scores_sabotage_and_territory_bonus_through_shared_boundary() -> None:
    setup = _sabotage_setup()
    territory_ids = _opponent_territory_non_home_objective_ids(setup, player_id="player-a")
    assert territory_ids
    state, record = _resolved_primary_action(
        layout_id="priority-assets-vs-priority-assets-layout-1",
        attacker_force_disposition_id="priority-assets",
        defender_force_disposition_id="priority-assets",
        player_id="player-a",
        mission_action_id=COMMIT_SABOTAGE_ACTION_ID,
        target_objective_id=territory_ids[0],
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert awards["each_friendly_unit_committed_sabotage_this_turn"] == 3
    assert awards["each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn"] == 2
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()


def _sabotage_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="priority-assets-vs-priority-assets-layout-1",
        attacker_force_disposition_id="priority-assets",
        defender_force_disposition_id="priority-assets",
    )


def _secure_asset_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="take-and-hold-vs-priority-assets-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="priority-assets",
    )


def _gather_intel_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="reconnaissance-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="reconnaissance",
    )


def _extract_relic_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="disruption-vs-priority-assets-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="priority-assets",
    )


def _non_home_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    home_roles = {ObjectiveMarkerRole.ATTACKER_HOME, ObjectiveMarkerRole.DEFENDER_HOME}
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role not in home_roles
    )


def _opponent_territory_non_home_objective_ids(
    setup: MissionSetup,
    *,
    player_id: str,
) -> tuple[str, ...]:
    opponent_id = next(
        candidate_id
        for candidate_id in (setup.attacker_player_id, setup.defender_player_id)
        if candidate_id != player_id
    )
    opponent_role = "attacker" if opponent_id == setup.attacker_player_id else "defender"
    territory = next(
        region
        for region in setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY
        and region.owner_role == opponent_role
    )
    excluded_home_ids = set(home_objective_ids(setup, player_id=player_id)) | set(
        home_objective_ids(setup, player_id=opponent_id)
    )
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id not in excluded_home_ids
        and territory.contains_point(marker.x_inches, marker.y_inches)
    )


def _completed_action(
    setup: MissionSetup,
    *,
    mission_action_id: str,
    unit_instance_id: str,
    target_id: str,
    action_index: int = 1,
    battle_round: int = 1,
    player_id: str = "player-a",
    mission_id: str | None = None,
) -> MissionActionState:
    policy = mission_action_policy_for_id(mission_action_id)
    assigned_mission_id = (
        mission_id if mission_id is not None else setup.primary_mission_id_for_player(player_id)
    )
    started = MissionActionState.start(
        action_id=f"step5c-action-{action_index:02d}",
        mission_action_id=mission_action_id,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=None,
        mission_id=assigned_mission_id,
        battle_round=battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing=policy.start_timing,
        completion_timing=policy.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=(),
        scoring_source_id=policy.scoring_source_id,
        victory_points=0,
    )
    return started.complete_without_award(
        battle_round=battle_round,
        phase=BattlePhase.FIGHT.value,
        completion_timing=policy.completion_timing,
    )


def _interrupted_action(
    setup: MissionSetup,
    *,
    mission_action_id: str,
    unit_instance_id: str,
    target_id: str,
    action_index: int,
) -> MissionActionState:
    policy = mission_action_policy_for_id(mission_action_id)
    started = MissionActionState.start(
        action_id=f"step5c-action-{action_index:02d}",
        mission_action_id=mission_action_id,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=None,
        mission_id=setup.primary_mission_id_for_player("player-a"),
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        start_timing=policy.start_timing,
        completion_timing=policy.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=("completion_condition_failed",),
        scoring_source_id=policy.scoring_source_id,
        victory_points=0,
    )
    return started.fail_completion()


def _resolved_primary_action(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    player_id: str,
    mission_action_id: str,
    target_objective_id: str | None = None,
) -> tuple[GameState, ObjectiveControlRecord]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
        player_id=player_id,
        mission_action_id=mission_action_id,
        current_phase=BattlePhase.FIGHT,
        target_objective_id=target_objective_id,
    )
    _bind_force_dispositions(state)
    if target_id != action.target_id:
        raise AssertionError("Step 5C Action turn-end target drifted.")
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    assert resolved[0].status is MissionActionStatus.COMPLETED
    return state, record


def _bind_force_dispositions(state: GameState) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5C fixture requires MissionSetup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]


def _objective_context(
    *,
    setup: MissionSetup,
    battle_round: int,
) -> PrimaryScoringConditionContext:
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(),
        )
        for marker in setup.objective_markers
    )
    record = ObjectiveControlRecord(
        record_id=f"step5c-objective-record-round-{battle_round}",
        game_id="step5c-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5c-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )


def _primary_awards_by_condition(state: GameState, *, player_id: str) -> dict[str, int]:
    awards: dict[str, int] = {}
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if (
                transaction.player_id != player_id
                or transaction.source_kind is not VictoryPointSourceKind.PRIMARY
                or type(transaction.metadata) is not dict
            ):
                continue
            condition = transaction.metadata.get("scoring_rule_condition")
            if type(condition) is not str:
                continue
            awards[condition] = transaction.amount
    return awards
