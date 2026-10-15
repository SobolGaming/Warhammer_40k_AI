from __future__ import annotations

from tests.shared.category_migration.phase17n_step5d_condemned_departure_conditions import (
    ANY_PLAYER_TURN,
    CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
    OWN_PLAYER_TURN,
    PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    PRIMARY_SCORING_DEPARTURE_CONDITIONS,
    PUNISHMENT_CHOICE_RULE_ID,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    BattlefieldRemovalKind,
    BattlePhase,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    EventLog,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    MissionSetup,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    PrimaryBattlefieldDepartureState,
    PrimaryCondemnedSelectionState,
    PrimaryMissionChoiceData,
    PrimaryMissionProgressState,
    PrimaryScoringBoundaryKind,
    PrimaryScoringConditionContext,
    RuntimeModifierRegistry,
    UnitMusterSelection,
    VictoryPointSourceKind,
    _assert_condemned_boundary_path,
    _bind_force_dispositions,
    _condemn_attached_option,
    _condemn_option,
    _condemned_selection,
    _depart_rules_unit,
    _departure,
    _destroy_component_for_scoring,
    _objective_context,
    _park_enemy_units_away_from_objectives,
    _place_owner_on_expansion,
    _primary_awards_by_condition,
    _progress,
    _punishment_setup,
    _resolved_condemned_attached_component_loss_departure,
    _resolved_condemned_departure,
    condemned_selection_source_identity,
    default_unit_selection,
    destroy_model_by_rule,
    evaluate_departure_scoring_condition,
    evaluate_primary_scoring_condition,
    event_primary_scoring,
    mission_scoring_policies_from_setup,
    phase17n_event_setup,
    phase17n_punishment_pending_fixture,
    primary_battlefield_departure_id,
    primary_condemned_selection_id,
    primary_mission_choice_rule_for_id,
    primary_own_turn_interval_contains,
    primary_scoring_rule_applies_at_record,
    primary_scoring_rules_from_definition,
    primary_scoring_turn_scope_for_condition,
    pytest,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    replace,
    required_primary_scoring_boundary_kinds,
    rules_unit_view_by_id,
    score_primary_objective_control_boundary,
    warhammer_event_companion_2026_07_mission_pack,
    with_model_offsets,
)


def test_phase17n_step5d_embark_and_reserves_count_as_left_battlefield() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("enemy-unit-1",))
    embark = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="embarked",
                removal_kind=BattlefieldRemovalKind.EMBARK,
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    reserves = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="reserves",
                removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert embark["score_count"] == 1
    assert reserves["score_count"] == 1


def test_phase17n_step5d_attached_unit_requires_every_component_to_leave() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("attached-enemy",))
    partial = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="leader-only",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-leader",),
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    complete = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="leader",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-leader",),
            ),
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="bodyguard",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-bodyguard",),
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert partial["score_count"] == 0
    assert complete["score_count"] == 1


@pytest.mark.parametrize(
    "removal_kind",
    [BattlefieldRemovalKind.EMBARK, BattlefieldRemovalKind.INTO_RESERVES],
)
def test_phase17n_step5d_mixed_attached_identities_score_after_component_loss(
    removal_kind: BattlefieldRemovalKind,
) -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("attached-enemy",))
    historical = _departure(
        rules_unit_instance_id="attached-enemy",
        occurrence_id="bodyguard-destroyed",
        component_ids=("attached-leader", "attached-bodyguard"),
        departed_ids=("attached-bodyguard",),
    )
    survivor = _departure(
        rules_unit_instance_id="attached-leader",
        occurrence_id="leader-left",
        component_ids=("attached-leader",),
        departed_ids=("attached-leader",),
        removal_kind=removal_kind,
    )
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(historical, survivor),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 1
    assert evidence["departed_condemned_rules_unit_instance_ids"] == ["attached-enemy"]
    assert evidence["matching_departure_ids"] == sorted(
        [historical.departure_id, survivor.departure_id]
    )


def test_phase17n_step5d_mixed_attached_identities_score_inverse_component_order() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("attached-enemy",))
    historical = _departure(
        rules_unit_instance_id="attached-enemy",
        occurrence_id="leader-destroyed",
        component_ids=("attached-leader", "attached-bodyguard"),
        departed_ids=("attached-leader",),
    )
    survivor = _departure(
        rules_unit_instance_id="attached-bodyguard",
        occurrence_id="bodyguard-embarked",
        component_ids=("attached-bodyguard",),
        departed_ids=("attached-bodyguard",),
        removal_kind=BattlefieldRemovalKind.EMBARK,
    )
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(historical, survivor),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 1
    assert evidence["matching_departure_ids"] == sorted(
        [historical.departure_id, survivor.departure_id]
    )


def test_phase17n_step5d_mixed_attached_identities_require_every_component() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("attached-enemy",))
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="bodyguard-destroyed",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-bodyguard",),
            ),
            _departure(
                rules_unit_instance_id="unrelated-enemy",
                occurrence_id="other-unit",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 0
    assert evidence["matching_departure_ids"] == []


def test_phase17n_step5d_rejects_mixed_attached_component_identity_drift() -> None:
    setup = _punishment_setup()
    with pytest.raises(GameLifecycleError, match="component identity drifted"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(_condemned_selection(selected_ids=("attached-enemy",))),
            departures=(
                _departure(
                    rules_unit_instance_id="attached-enemy",
                    occurrence_id="bodyguard",
                    component_ids=("attached-leader", "attached-bodyguard"),
                    departed_ids=("attached-bodyguard",),
                ),
                _departure(
                    rules_unit_instance_id="attached-enemy",
                    occurrence_id="other-lineage",
                    component_ids=("attached-leader", "attached-other"),
                    departed_ids=("attached-other",),
                ),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
            turn_order=("player-a", "player-b"),
        )


def test_phase17n_step5d_own_turn_objective_rule_does_not_apply_on_opponent_turn() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary = next(
        mission
        for mission in package.primary_missions
        if mission.primary_mission_id == "primary-punishment"
    )
    objective_rule = next(
        rule
        for rule in primary_scoring_rules_from_definition(primary)
        if rule.rule_id == "punishment-objective-control"
    )
    setup = _punishment_setup()
    record = ObjectiveControlRecord(
        record_id="step5d-r5-opponent-turn-end",
        game_id="step5d-objective-game",
        battle_round=5,
        active_player_id="player-b",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5d-objective-battlefield",
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=marker.objective_marker_id,
                contributors=(),
            )
            for marker in setup.objective_markers
        ),
    )
    policy = mission_scoring_policies_from_setup(setup).policy_for_player("player-a")
    assert not primary_scoring_rule_applies_at_record(
        timing=objective_rule.timing,
        condition=objective_rule.condition,
        record=record,
        scoring_player_id="player-a",
        primary_scoring_phase=policy.primary_scoring_phase,
        primary_scoring_timing=policy.primary_scoring_timing,
        game_length_battle_rounds=policy.game_length_battle_rounds,
        end_of_battle=False,
    )
    assert primary_scoring_rule_applies_at_record(
        timing="turn_end",
        condition=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        record=record,
        scoring_player_id="player-a",
        primary_scoring_phase=policy.primary_scoring_phase,
        primary_scoring_timing=policy.primary_scoring_timing,
        game_length_battle_rounds=policy.game_length_battle_rounds,
        end_of_battle=False,
    )


@pytest.mark.parametrize(
    ("destroyed_component", "removal_kind"),
    [
        ("bodyguard", BattlefieldRemovalKind.EMBARK),
        ("bodyguard", BattlefieldRemovalKind.INTO_RESERVES),
        ("leader", BattlefieldRemovalKind.EMBARK),
        ("leader", BattlefieldRemovalKind.INTO_RESERVES),
    ],
)
def test_phase17n_step5d_scores_mixed_attached_identity_after_component_loss(
    destroyed_component: str,
    removal_kind: BattlefieldRemovalKind,
) -> None:
    state, record, decisions, attached_id, survivor_id = (
        _resolved_condemned_attached_component_loss_departure(
            destroyed_component=destroyed_component,
            surviving_removal_kind=removal_kind,
        )
    )
    rules_ids = {
        departure.rules_unit_instance_id for departure in state.primary_battlefield_departure_states
    }
    assert attached_id in rules_ids
    assert survivor_id not in rules_ids
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-a",
        expected_vp=5,
    )


def test_phase17n_step5d_mixed_attached_component_loss_without_survivor_departure_scores_zero() -> (
    None
):
    state, record, decisions, attached_id, survivor_id = (
        _resolved_condemned_attached_component_loss_departure(
            destroyed_component="bodyguard",
            surviving_removal_kind=BattlefieldRemovalKind.EMBARK,
            depart_survivor=False,
        )
    )
    rules_ids = {
        departure.rules_unit_instance_id for departure in state.primary_battlefield_departure_states
    }
    assert attached_id in rules_ids
    assert survivor_id not in rules_ids
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-a",
        expected_vp=0,
    )


__all__: list[str] = []
__all__ += ["ANY_PLAYER_TURN", "DecisionController", "DecisionOption", "DecisionRequest"]
__all__ += ["DecisionResult", "EventLog", "GameLifecycle", "GameState", "MissionSetup"]
__all__ += ["OWN_PLAYER_TURN", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "PRIMARY_SCORING_DEPARTURE_CONDITIONS"]
__all__ += ["PUNISHMENT_CHOICE_RULE_ID", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryCondemnedSelectionState", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionProgressState", "PrimaryScoringBoundaryKind"]
__all__ += ["PrimaryScoringConditionContext", "RuntimeModifierRegistry"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "UnitMusterSelection"]
__all__ += ["VictoryPointSourceKind", "_bind_force_dispositions", "_condemn_attached_option"]
__all__ += ["_condemn_option", "_depart_rules_unit", "_destroy_component_for_scoring"]
__all__ += ["_objective_context", "_park_enemy_units_away_from_objectives"]
__all__ += ["_place_owner_on_expansion", "_primary_awards_by_condition"]
__all__ += ["_resolved_condemned_departure", "condemned_selection_source_identity"]
__all__ += ["default_unit_selection", "destroy_model_by_rule"]
__all__ += ["evaluate_primary_scoring_condition", "event_primary_scoring", "phase17n_event_setup"]
__all__ += ["phase17n_punishment_pending_fixture", "primary_battlefield_departure_id"]
__all__ += ["primary_condemned_selection_id", "primary_mission_choice_rule_for_id"]
__all__ += ["primary_own_turn_interval_contains", "primary_scoring_turn_scope_for_condition"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "replace"]
__all__ += ["required_primary_scoring_boundary_kinds", "rules_unit_view_by_id"]
__all__ += ["score_primary_objective_control_boundary", "with_model_offsets"]
