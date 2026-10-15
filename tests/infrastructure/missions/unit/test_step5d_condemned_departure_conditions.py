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


def test_phase17n_step5d_departure_conditions_are_registered() -> None:
    assert PRIMARY_SCORING_DEPARTURE_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN in (
        SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    )


def test_phase17n_step5d_promotes_punishment() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    rules = primary_scoring_rules_from_definition(primary_by_id["primary-punishment"])
    assert rules
    assert all(rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS for rule in rules)
    assert any(rule.condition == CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN for rule in rules)
    artifact = event_primary_scoring.event_companion_primary_scoring_artifact()
    punishment = next(
        mission
        for mission in artifact.primary_missions
        if mission.primary_mission_id == "primary-punishment"
    )
    scopes = {rule.rule_id: rule.turn_scope for rule in punishment.scoring_rules}
    assert scopes["punishment-condemned-left-battlefield"] == ANY_PLAYER_TURN
    assert all(
        scope == OWN_PLAYER_TURN
        for rule_id, scope in scopes.items()
        if rule_id != "punishment-condemned-left-battlefield"
    )
    assert {
        CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN
    } == PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS
    assert (
        primary_scoring_turn_scope_for_condition(CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN)
        == ANY_PLAYER_TURN
    )
    assert primary_scoring_turn_scope_for_condition("each_controlled_objective") == OWN_PLAYER_TURN
    assert (
        primary_scoring_turn_scope_for_condition(
            "one_or_more_enemy_units_destroyed_after_starting_turn_in_trapped_terrain"
        )
        == OWN_PLAYER_TURN
    )


def test_phase17n_step5d_departure_conditions_require_state_evidence() -> None:
    setup = _punishment_setup()
    context = _objective_context(setup=setup, battle_round=1)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            context=context,
        )


def test_phase17n_step5d_scores_boolean_once_when_condemned_unit_fully_left() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(
        selected_ids=("enemy-unit-1", "enemy-unit-2"),
    )
    matching = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(rules_unit_instance_id="enemy-unit-1", occurrence_id="left-1"),
            _departure(rules_unit_instance_id="enemy-unit-2", occurrence_id="left-2"),
            _departure(
                rules_unit_instance_id="enemy-unit-3",
                occurrence_id="non-condemned",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert matching["score_count"] == 1
    assert matching["departed_condemned_rules_unit_instance_ids"] == [
        "enemy-unit-1",
        "enemy-unit-2",
    ]


def test_phase17n_step5d_empty_or_missing_condemned_selection_scores_zero() -> None:
    setup = _punishment_setup()
    empty = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(_condemned_selection(selected_ids=())),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    missing = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=PrimaryMissionProgressState.empty(),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert empty["score_count"] == 0
    assert missing["score_count"] == 0


def test_phase17n_step5d_ignores_non_condemned_partial_other_round_and_other_turn() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("enemy-unit-1",))
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-2",
                occurrence_id="other-unit",
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="partial",
                departed=False,
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="other-round",
                battle_round=2,
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="other-turn",
                active_player_id="player-b",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 0


def test_phase17n_step5d_ignores_other_mission_round_and_player_selections() -> None:
    setup = _punishment_setup()
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                mission_id="primary-delaying-action",
                selection_index=1,
            ),
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                battle_round=2,
                selection_index=2,
            ),
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                owner_player_id="player-b",
                selection_index=3,
            ),
        ),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 0


def test_phase17n_step5d_rejects_duplicate_departure_ids() -> None:
    setup = _punishment_setup()
    departure = _departure(rules_unit_instance_id="enemy-unit-1")
    with pytest.raises(GameLifecycleError, match="must not duplicate departure_id"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(_condemned_selection(selected_ids=("enemy-unit-1",))),
            departures=(departure, departure),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
            turn_order=("player-a", "player-b"),
        )


def test_phase17n_step5d_rejects_condemned_selection_source_identity_drift() -> None:
    setup = _punishment_setup()
    selection = _condemned_selection(
        selected_ids=("enemy-unit-1",),
        source_rule_id="forged-punishment-source",
    )
    with pytest.raises(GameLifecycleError, match="source identity drifted"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(selection),
            departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
            turn_order=("player-a", "player-b"),
        )


def test_phase17n_step5d_rejects_friendly_condemned_departure_owner() -> None:
    setup = _punishment_setup()
    with pytest.raises(GameLifecycleError, match="condemned departure owner drifted"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(_condemned_selection(selected_ids=("friendly-unit-1",))),
            departures=(
                _departure(
                    rules_unit_instance_id="friendly-unit-1",
                    owner_player_id="player-a",
                ),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
            turn_order=("player-a", "player-b"),
        )


def test_phase17n_step5d_scores_opponent_turn_departure_for_active_selection() -> None:
    setup = _punishment_setup()
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(_condemned_selection(selected_ids=("enemy-unit-1",), battle_round=2)),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                battle_round=2,
                active_player_id="player-b",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        active_player_id="player-b",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 1


def test_phase17n_step5d_scores_second_player_selection_across_round_rollover() -> None:
    setup = _punishment_setup(
        attacker_player_id="player-b",
        defender_player_id="player-a",
    )
    selection = _condemned_selection(
        selected_ids=("enemy-unit-1",),
        owner_player_id="player-b",
        battle_round=2,
    )
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(selection),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                owner_player_id="player-a",
                battle_round=3,
                active_player_id="player-a",
            ),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=3,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 1
    assert primary_own_turn_interval_contains(
        owner_player_id="player-b",
        started_battle_round=2,
        query_battle_round=3,
        query_active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )


def test_phase17n_step5d_expired_selection_does_not_score_on_owners_next_turn() -> None:
    setup = _punishment_setup()
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(_condemned_selection(selected_ids=("enemy-unit-1",), battle_round=2)),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                battle_round=3,
                active_player_id="player-a",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=3,
        active_player_id="player-a",
        turn_order=("player-a", "player-b"),
    )
    assert evidence["score_count"] == 0


def test_phase17n_step5d_scores_condemned_departure_through_shared_boundary() -> None:
    state, record, decisions = _resolved_condemned_departure()
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-a",
        expected_vp=5,
    )


def test_phase17n_step5d_shared_boundary_scores_zero_without_departure() -> None:
    state, record, decisions = _resolved_condemned_departure(depart_selected=False)
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-a",
        expected_vp=0,
    )


@pytest.mark.parametrize(
    (
        "attacker_player_id",
        "defender_player_id",
        "owner_player_id",
        "selection_battle_round",
        "departure_battle_round",
        "departure_active_player_id",
        "expected_vp",
    ),
    [
        ("player-a", "player-b", "player-a", 2, 2, "player-a", 5),
        ("player-a", "player-b", "player-a", 2, 2, "player-b", 5),
        ("player-b", "player-a", "player-b", 2, 3, "player-a", 5),
        ("player-b", "player-a", "player-b", 3, 3, "player-b", 5),
        ("player-a", "player-b", "player-a", 2, 3, "player-b", 0),
    ],
    ids=(
        "owner-a-own-turn",
        "owner-a-opponent-turn",
        "owner-b-second-player-rollover",
        "owner-b-own-later-round",
        "owner-a-expired-selection",
    ),
)
def test_phase17n_step5d_scores_condemned_departure_across_turn_windows(
    attacker_player_id: str,
    defender_player_id: str,
    owner_player_id: str,
    selection_battle_round: int,
    departure_battle_round: int,
    departure_active_player_id: str,
    expected_vp: int,
) -> None:
    state, record, decisions = _resolved_condemned_departure(
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
        owner_player_id=owner_player_id,
        selection_battle_round=selection_battle_round,
        departure_battle_round=departure_battle_round,
        departure_active_player_id=departure_active_player_id,
    )
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id=owner_player_id,
        expected_vp=expected_vp,
    )


@pytest.mark.parametrize(
    "removal_kind",
    [
        BattlefieldRemovalKind.DESTROYED,
        BattlefieldRemovalKind.EMBARK,
        BattlefieldRemovalKind.INTO_RESERVES,
    ],
)
def test_phase17n_step5d_scores_opponent_turn_departure_kinds(
    removal_kind: BattlefieldRemovalKind,
) -> None:
    state, record, decisions = _resolved_condemned_departure(
        selection_battle_round=2,
        departure_battle_round=2,
        departure_active_player_id="player-b",
        removal_kind=removal_kind,
    )
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-a",
        expected_vp=5,
    )


@pytest.mark.parametrize(
    "removal_kind",
    [
        BattlefieldRemovalKind.DESTROYED,
        BattlefieldRemovalKind.EMBARK,
        BattlefieldRemovalKind.INTO_RESERVES,
    ],
)
def test_phase17n_step5d_scores_second_player_rollover_departure_kinds(
    removal_kind: BattlefieldRemovalKind,
) -> None:
    state, record, decisions = _resolved_condemned_departure(
        attacker_player_id="player-b",
        defender_player_id="player-a",
        owner_player_id="player-b",
        selection_battle_round=2,
        departure_battle_round=3,
        departure_active_player_id="player-a",
        removal_kind=removal_kind,
    )
    _assert_condemned_boundary_path(
        state=state,
        record=record,
        decisions=decisions,
        owner_player_id="player-b",
        expected_vp=5,
    )


def test_phase17n_step5d_includes_non_active_punishment_owner_in_scoring_players() -> None:
    state, record, _decisions = _resolved_condemned_departure(
        selection_battle_round=2,
        departure_battle_round=2,
        departure_active_player_id="player-b",
    )
    assert state.mission_setup is not None
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    scoring_ids = policies.scoring_player_ids_for_record(
        record=record,
        turn_order=tuple(state.turn_order),
        end_of_battle=False,
    )
    assert scoring_ids == ("player-a", "player-b")
    assert record.active_player_id == "player-b"


def test_phase17n_step5d_caps_opponent_turn_condemned_award() -> None:
    player_b_units = (
        default_unit_selection("intercessor-unit-3"),
        default_unit_selection("intercessor-unit-4"),
    )
    state, own_record, decisions = _resolved_condemned_departure(
        selection_battle_round=2,
        departure_battle_round=2,
        departure_active_player_id="player-a",
        player_b_units=player_b_units,
        selected_count=2,
        depart_unit_index=0,
        score_owner_command=True,
    )
    score_primary_objective_control_boundary(
        state=state,
        record=own_record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    remaining_id = state.primary_mission_progress_state.condemned_selections[
        0
    ].selected_rules_unit_instance_ids[1]
    _depart_rules_unit(
        state=state,
        decisions=decisions,
        rules_unit_instance_id=remaining_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="step5d-cap-second-departure",
        battle_round=2,
        active_player_id="player-b",
    )
    opponent_record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    score_primary_objective_control_boundary(
        state=state,
        record=opponent_record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    ledger = state.victory_point_ledger_for_player("player-a")
    round_two_primary = sum(
        transaction.amount
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
        and transaction.battle_round == 2
    )
    assert round_two_primary == 15
    capped = next(
        transaction
        for transaction in ledger.transactions
        if type(transaction.metadata) is dict
        and transaction.metadata.get("vp_cap_audit") is not None
        and transaction.metadata.get("scoring_rule_condition")
        == CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN
    )
    assert capped.amount == 1
    assert type(capped.metadata) is dict
    cap_audit = capped.metadata["vp_cap_audit"]
    assert type(cap_audit) is dict
    assert cap_audit["requested_amount"] == 5
    assert cap_audit["applied_amount"] == 1
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()


__all__: list[str] = []
__all__ += ["DecisionController", "DecisionOption", "DecisionRequest", "DecisionResult"]
__all__ += ["EventLog", "GameLifecycle", "MissionSetup", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlResult", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "PUNISHMENT_CHOICE_RULE_ID"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryCondemnedSelectionState"]
__all__ += ["PrimaryMissionChoiceData", "PrimaryScoringBoundaryKind"]
__all__ += ["PrimaryScoringConditionContext", "UnitMusterSelection", "_bind_force_dispositions"]
__all__ += ["_condemn_attached_option", "_condemn_option", "_destroy_component_for_scoring"]
__all__ += ["_park_enemy_units_away_from_objectives", "_place_owner_on_expansion"]
__all__ += ["_primary_awards_by_condition"]
__all__ += ["_resolved_condemned_attached_component_loss_departure"]
__all__ += ["condemned_selection_source_identity", "destroy_model_by_rule"]
__all__ += ["phase17n_event_setup", "phase17n_punishment_pending_fixture"]
__all__ += ["primary_battlefield_departure_id", "primary_condemned_selection_id"]
__all__ += ["primary_mission_choice_rule_for_id", "primary_scoring_rule_applies_at_record"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "replace"]
__all__ += ["required_primary_scoring_boundary_kinds", "rules_unit_view_by_id"]
__all__ += ["with_model_offsets"]
