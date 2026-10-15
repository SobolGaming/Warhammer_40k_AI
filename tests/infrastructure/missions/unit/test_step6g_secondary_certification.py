from __future__ import annotations

from tests.shared.category_migration.phase17n_step6g_secondary_certification import (
    _LAYOUT_ROW,
    _LIFECYCLE_CERTIFICATION_ROWS,
    _SCORING_PLAYER_IDS,
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    SELECT_BEACON_UNIT_DECISION_TYPE,
    SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
    SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
    STEP6G_MISSION_PARTITIONS,
    TURN_CAP_TACTICAL_IDS,
    ArmyDefinition,
    AttachmentDeclaration,
    BattlePhase,
    DecisionController,
    DecisionError,
    DecisionResult,
    FiniteOptionSubmission,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    LifecycleStatusKind,
    LocalGameSession,
    ModelPlacement,
    ObjectiveControlTiming,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    Pose,
    PrimaryUnattributedDestructionCause,
    ReserveKind,
    ReserveState,
    RulesUnitPresence,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SecondaryMissionSelection,
    UnitInstance,
    _attached_burden_state,
    _command_tactical_state,
    _configured_step6g_lifecycle,
    _decisions_for_seeded_secondary_state,
    _first_intercessor,
    _home_objective,
    _lifecycle_row,
    _place_unit,
    _record_unresolved_tactical,
    _restore_unit_wounds,
    _score_certified_row_from_state,
    _secondary_transactions,
    _seed_completed_fight_phase,
    _seed_single_tactical_card,
    _setup_for_layout,
    _tactical_fight_state,
    _turn_cap_state,
    _unit_by_id,
    _unit_for,
    _zero_and_remove_unit,
    apply_tactical_secondary_when_drawn,
    army_muster_request,
    attached_when_drawn_state,
    certification_unit_selections,
    complete_setup_through_gate,
    create_deterministic_battlefield_scenario,
    deepcopy,
    default_unit_selection,
    mustered_armies,
    next_secondary_mission_choice_request,
    next_tactical_secondary_when_drawn_request,
    phase11c_config,
    phase17n_state_with_setup,
    pytest,
    record_existing_primary_turn_start_evidence_events_for_fixture,
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
    record_primary_turn_start_evidence_for_fixture,
    record_secondary_destruction_for_fixture,
    record_unresolved_when_drawn_card,
    replace,
    reposition_destruction_policy,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
    resolved_secondary_mission_selection_for_card,
    score_turn_end_mission_scoring_boundary,
    secondary_mission_inventory_rows,
    secondary_mission_selection_for_card,
    seed_sequential_tactical_turn_cap_conditions,
    step6g_matrix_case_keys,
    unit_selection,
    validate_attached_rules_unit_identity_after_destruction,
)


def test_zero_secondary_turn_capacity_cannot_score_or_discard_an_achieved_tactical() -> None:
    state, decisions = _turn_cap_state()
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]:
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
        transactions = _secondary_transactions(
            state,
            player_id="player-a",
            source_id=secondary_mission_id,
        )
        assert len(transactions) == 1
        assert transactions[0].amount == 5
    capped_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    current_records = tuple(
        record
        for record in state.objective_control_records
        if record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    assert len(current_records) == 1
    ordinary_discard_state_payload = deepcopy(state.to_payload())
    ordinary_discard_decisions_payload = deepcopy(decisions.to_payload())
    score_turn_end_mission_scoring_boundary(
        state=state,
        record=current_records[0],
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == capped_secondary_id
    )
    ledger_before = state.victory_point_ledger_for_player("player-a")

    with pytest.raises(GameLifecycleError, match="must award at least 1 VP"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=capped_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )

    assert state.victory_point_ledger_for_player("player-a") == ledger_before
    assert (
        _secondary_transactions(
            state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    active = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=capped_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active is not None
    assert active.status is SecondaryMissionCardStatus.ACTIVE
    assert state.tactical_secondary_achievement_context(achievement.achievement_id) == achievement

    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=achievement,
    )
    assert waiting.decision_request is not None
    score_session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(state=state, decisions=decisions)
    )
    score_state = score_session.lifecycle.state
    assert score_state is not None
    request = score_session.lifecycle.pending_decision_request()
    assert request is not None
    assert [option.option_id for option in request.options] == [f"retain:{capped_secondary_id}"]
    with pytest.raises(DecisionError, match="finite action space"):
        score_session.submit_option(
            request_id=request.request_id,
            option_id=f"score:{capped_secondary_id}",
            result_id="phase17n-zero-cap-illegal-score",
        )
    assert score_session.lifecycle.pending_decision_request() == request
    assert (
        score_state.tactical_secondary_achievement_context(achievement.achievement_id)
        == achievement
    )
    assert (
        score_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=capped_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        == active
    )
    assert [option.option_id for option in request.options] == [f"retain:{capped_secondary_id}"]
    assert (
        _secondary_transactions(
            score_state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    GameLifecycle.from_payload(deepcopy(score_session.lifecycle.to_payload()))

    discard_state = GameState.from_payload(ordinary_discard_state_payload)
    discard_card_battle_round = discard_state.battle_round
    discard_decisions = DecisionController.from_payload(ordinary_discard_decisions_payload)
    discard_waiting = request_tactical_secondary_discard(
        state=discard_state,
        decisions=discard_decisions,
        player_id="player-a",
    )
    assert discard_waiting.decision_request is not None
    discard_session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(
            state=discard_state,
            decisions=discard_decisions,
        )
    )
    discard_request = discard_session.lifecycle.pending_decision_request()
    assert discard_request is not None
    discard_option = next(
        option.option_id
        for option in discard_request.options
        if option.option_id == f"discard:{capped_secondary_id}"
    )
    discard_session.submit_option(
        request_id=discard_request.request_id,
        option_id=discard_option,
        result_id="phase17n-zero-cap-ordinary-discard",
    )
    discarded_state = discard_session.lifecycle.state
    assert discarded_state is not None
    discarded = next(
        card
        for card in discarded_state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == capped_secondary_id
        and card.battle_round == discard_card_battle_round
    )
    assert discarded.status is SecondaryMissionCardStatus.DISCARDED
    assert (
        _secondary_transactions(
            discarded_state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    assert not any(
        event.event_type == "tactical_secondary_mission_scored"
        for event in discard_session.lifecycle.decision_controller.event_log.records
    )
    GameLifecycle.from_payload(deepcopy(discard_session.lifecycle.to_payload()))


def test_tactical_score_rejects_stale_result_after_other_cards_exhaust_turn_cap() -> None:
    state, decisions = _turn_cap_state()
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT,
        runtime_modifier_registry=None,
    )
    score_turn_end_mission_scoring_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    target_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    target_achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == target_secondary_id
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=target_achievement,
    )
    request = waiting.decision_request
    assert request is not None
    assert {option.option_id for option in request.options} == {
        f"score:{target_secondary_id}",
        f"retain:{target_secondary_id}",
    }
    stale_score_result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{target_secondary_id}",
        result_id="phase17n-stale-tactical-score-after-turn-cap",
    ).to_result(request)

    for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]:
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
    assert (
        sum(
            transaction.amount
            for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]
            for transaction in _secondary_transactions(
                state,
                player_id="player-a",
                source_id=secondary_mission_id,
            )
        )
        == 15
    )
    lifecycle = _configured_step6g_lifecycle(state=state, decisions=decisions)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    pending_before = lifecycle.pending_decision_request()
    assert pending_before == request
    ledger_before = lifecycle_state.victory_point_ledger_for_player("player-a")
    records_before = lifecycle.decision_controller.records
    active_before = lifecycle_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=target_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active_before is not None
    achievement_before = lifecycle_state.tactical_secondary_achievement_context(
        target_achievement.achievement_id
    )
    assert achievement_before is not None

    status = lifecycle.submit_decision(stale_score_result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["invalid_reason"] == "victory_point_capacity_exhausted"
    assert lifecycle.pending_decision_request() == pending_before
    assert lifecycle.decision_controller.records == records_before
    assert lifecycle_state.victory_point_ledger_for_player("player-a") == ledger_before
    assert (
        _secondary_transactions(
            lifecycle_state,
            player_id="player-a",
            source_id=target_secondary_id,
        )
        == ()
    )
    assert (
        lifecycle_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=target_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        == active_before
    )
    assert (
        lifecycle_state.tactical_secondary_achievement_context(target_achievement.achievement_id)
        == achievement_before
    )


def test_delayed_tactical_score_reuses_boundary_evidence_after_selection_resolution() -> None:
    state, decisions = _turn_cap_state()
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT,
        runtime_modifier_registry=None,
    )

    score_turn_end_mission_scoring_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )

    target_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == target_secondary_id
    )
    active_card = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=target_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active_card is not None
    resolved_selection = secondary_mission_selection_for_card(active_card)
    assert resolved_selection is not None
    assert record.record_id in resolved_selection.resolved_objective_control_record_ids
    evidence_before = tuple(
        evidence
        for evidence in state.secondary_scoring_state_evidence_records
        if evidence.scoring_player_id == "player-a"
        and evidence.secondary_mission_id == target_secondary_id
        and evidence.objective_control_record_id == record.record_id
    )
    assert len(evidence_before) == 1
    assert evidence_before[0].selection_payload != active_card.selection_payload

    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=achievement,
    )
    request = waiting.decision_request
    assert request is not None
    session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(state=state, decisions=decisions)
    )

    status = session.submit_option(
        request_id=request.request_id,
        option_id=f"score:{target_secondary_id}",
        result_id="phase17n-delayed-tactical-score-reuses-boundary-evidence",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    scored_state = session.lifecycle.state
    assert scored_state is not None
    evidence_after = tuple(
        evidence
        for evidence in scored_state.secondary_scoring_state_evidence_records
        if evidence.scoring_player_id == "player-a"
        and evidence.secondary_mission_id == target_secondary_id
        and evidence.objective_control_record_id == record.record_id
    )
    assert evidence_after == evidence_before
    transactions = _secondary_transactions(
        scored_state,
        player_id="player-a",
        source_id=target_secondary_id,
    )
    assert len(transactions) == 1
    metadata = transactions[0].metadata
    assert isinstance(metadata, dict)
    assert metadata["secondary_scoring_state_evidence_id"] == evidence_before[0].evidence_id
    assert metadata["secondary_scoring_state_evidence_hash"] == evidence_before[0].evidence_hash


def test_positive_partial_tactical_award_scores_and_discards_the_card() -> None:
    state, decisions = _turn_cap_state()
    for secondary_mission_id, expected_amount in (
        ("a-tempting-target", 5),
        ("centre-ground", 5),
        ("behind-enemy-lines", 3),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
        assert (
            _secondary_transactions(
                state,
                player_id="player-a",
                source_id=secondary_mission_id,
            )[0].amount
            == expected_amount
        )

    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    transaction = _secondary_transactions(
        state,
        player_id="player-a",
        source_id="plunder",
    )[0]
    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert transaction.amount == 2
    assert isinstance(transaction.metadata, dict)
    audit = transaction.metadata["vp_cap_audit"]
    assert isinstance(audit, dict)
    assert audit["requested_amount"] == 5
    assert audit["applied_amount"] == 2
    assert audit["secondary_turn_points_before"] == 13
    assert audit["secondary_turn_points_after"] == 15
    assert audit["secondary_turn_remaining_capacity"] == 0
    GameState.from_payload(state.to_payload())


def test_spatial_secondary_restore_survives_later_qualifying_unit_mutation() -> None:
    row = _lifecycle_row("engage-on-all-fronts", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    qualifying_unit = _first_intercessor(state, player_id="player-a")
    _zero_and_remove_unit(state, qualifying_unit.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="engage-on-all-fronts",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == expectation.expected_amount


def test_unattributed_and_self_destruction_score_bring_it_down() -> None:
    unattributed_state = _tactical_fight_state()
    unattributed_state.battle_round = 3
    unattributed_state.active_player_id = "player-b"
    _seed_completed_fight_phase(unattributed_state)
    _seed_single_tactical_card(unattributed_state, "bring-it-down")
    reserve_vehicle = _unit_for(
        unattributed_state,
        player_id="player-b",
        datasheet_id="core-vehicle-monster",
    )
    battlefield = unattributed_state.battlefield_state
    mission_setup = unattributed_state.mission_setup
    assert battlefield is not None
    assert mission_setup is not None
    unattributed_state.replace_battlefield_state(
        battlefield.without_unit_placement(reserve_vehicle.unit_instance_id)
    )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-b",
        unit_instance_id=reserve_vehicle.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    unattributed_state.record_reserve_state(declared_reserve)
    unattributed_decisions = DecisionController()
    unattributed_decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": unattributed_state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    record_primary_turn_start_evidence_for_fixture(
        unattributed_state,
        decisions=unattributed_decisions,
    )
    destruction_ids_before = tuple(
        destruction.destruction_id
        for destruction in unattributed_state.primary_unit_destruction_states
    )
    unattributed_state._resolve_unarrived_reserve_destruction_boundary(  # pyright: ignore[reportPrivateUsage]
        end_of_battle=False
    )
    record_new_primary_unit_destruction_events(
        state=unattributed_state,
        event_log=unattributed_decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    (unattributed_destruction,) = tuple(
        destruction
        for destruction in unattributed_state.secondary_unit_destruction_states
        if destruction.destroyed_unit_instance_id == reserve_vehicle.unit_instance_id
    )
    assert unattributed_destruction.destroying_player_id is None
    primary_destruction = next(
        destruction
        for destruction in unattributed_state.primary_unit_destruction_states
        if destruction.destruction_id == unattributed_destruction.source_primary_destruction_id
    )
    assert (
        primary_destruction.unattributed_cause
        is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
    )
    unattributed_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=unattributed_decisions.event_log,
    )
    unattributed_transactions = _secondary_transactions(
        unattributed_state,
        player_id="player-a",
        source_id="bring-it-down",
    )
    assert unattributed_transactions[0].amount == 5
    restored_unattributed_lifecycle = _configured_step6g_lifecycle(
        state=unattributed_state,
        decisions=unattributed_decisions,
    )
    restored_unattributed_state = restored_unattributed_lifecycle.state
    assert restored_unattributed_state is not None
    assert restored_unattributed_state.to_payload() == unattributed_state.to_payload()
    assert (
        GameLifecycle.from_payload(
            deepcopy(restored_unattributed_lifecycle.to_payload())
        ).to_payload()
        == restored_unattributed_lifecycle.to_payload()
    )

    self_kill_state = _tactical_fight_state()
    _seed_single_tactical_card(self_kill_state, "bring-it-down")
    vehicle = _unit_for(
        self_kill_state,
        player_id="player-b",
        datasheet_id="core-vehicle-monster",
    )
    decisions = record_primary_turn_start_evidence_for_fixture(self_kill_state)
    record_secondary_destruction_for_fixture(
        self_kill_state,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=vehicle.unit_instance_id,
        source_id="phase17n-self-kill-bring-it-down",
        event_log=decisions.event_log,
    )
    self_kill_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    assert (
        _secondary_transactions(
            self_kill_state,
            player_id="player-a",
            source_id="bring-it-down",
        )[0].amount
        == 5
    )


def test_assassination_all_destroyed_survives_character_return_to_life() -> None:
    row = _lifecycle_row("assassination", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    character = _unit_for(
        state,
        player_id="player-b",
        datasheet_id="core-character-leader",
    )
    _restore_unit_wounds(state, character.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="assassination",
    )
    assert transactions[0].amount == expectation.expected_amount
    metadata = transactions[0].metadata
    if type(metadata) is not dict:
        raise AssertionError("Assassination transaction metadata must be an object.")
    assert metadata["scoring_rule_ids"] == ["assassination-tactical-all-characters-destroyed"]


def test_cleanse_when_drawn_shuffle_is_optional_while_plunder_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "plunder")
    _record_unresolved_tactical(state, "cleanse")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert status is not None
    request = status.decision_request
    assert request is not None
    request_payload = request.payload
    assert isinstance(request_payload, dict)
    assert request_payload["secondary_mission_id"] == "cleanse"
    assert [option.option_id for option in request.options] == [
        "keep:cleanse",
        "shuffle:cleanse",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-shuffle-cleanse",
            request=request,
            selected_option_id="shuffle:cleanse",
        ),
        decisions=decisions,
    )
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="cleanse",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    plunder = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert plunder is not None
    assert plunder.status is SecondaryMissionCardStatus.ACTIVE


def test_plunder_when_drawn_shuffle_is_optional_while_cleanse_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "cleanse")
    _record_unresolved_tactical(state, "plunder")
    decisions = DecisionController()
    first = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert first is not None
    assert first.decision_request is not None
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-cleanse",
            request=first.decision_request,
            selected_option_id="keep:cleanse",
        ),
        decisions=decisions,
    )
    second = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert second is not None
    assert second.decision_request is not None
    second_payload = second.decision_request.payload
    assert isinstance(second_payload, dict)
    assert second_payload["secondary_mission_id"] == "plunder"
    assert [option.option_id for option in second.decision_request.options] == [
        "keep:plunder",
        "shuffle:plunder",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-plunder",
            request=second.decision_request,
            selected_option_id="keep:plunder",
        ),
        decisions=decisions,
    )
    assert next_tactical_secondary_when_drawn_request(state=state, decisions=decisions) is None
    for secondary_mission_id in ("cleanse", "plunder"):
        card = state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        assert card is not None
        assert card.status is SecondaryMissionCardStatus.ACTIVE


def test_defend_stronghold_first_round_when_drawn_shuffles_without_keep_option() -> None:
    state = _command_tactical_state(battle_round=1)
    _record_unresolved_tactical(state, "defend-stronghold")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    shuffled = [
        event
        for event in decisions.event_log.records
        if event.event_type == "tactical_secondary_when_drawn_shuffled"
    ]
    assert len(shuffled) == 1
    payload = shuffled[0].payload
    if type(payload) is not dict:
        raise AssertionError("Defend Stronghold When Drawn event payload must be an object.")
    assert payload["mandatory"] is True
    assert payload["secondary_mission_id"] == "defend-stronghold"
    if status is not None and status.decision_request is not None:
        status_payload = status.decision_request.payload
        assert isinstance(status_payload, dict)
        assert status_payload["secondary_mission_id"] != "defend-stronghold"
        assert all(
            not option.option_id.startswith("keep:defend-stronghold")
            for option in status.decision_request.options
        )


def test_a_grievous_blow_when_drawn_allows_discard_below_13_models() -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=11,
        secondary_mission_id="a-grievous-blow",
    )
    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    assert status is not None
    assert status.decision_request is not None
    assert {option.option_id for option in status.decision_request.options} == {
        "keep:a-grievous-blow",
        "discard:a-grievous-blow",
    }


__all__: list[str] = []
__all__ += ["ArmyDefinition", "AttachmentDeclaration", "GameLifecycleStage", "ModelPlacement"]
__all__ += ["ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "Pose", "RulesUnitPresence"]
__all__ += ["SECONDARY_CARD_MODE_CERTIFICATION_COUNT", "SECONDARY_LIFECYCLE_CERTIFICATION_COUNT"]
__all__ += ["SECONDARY_MISSION_COUNT", "SELECT_BEACON_UNIT_DECISION_TYPE"]
__all__ += ["SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE"]
__all__ += ["SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE", "STEP6G_MISSION_PARTITIONS"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["_LAYOUT_ROW", "SecondaryMissionSelection", "UnitInstance"]
__all__ += ["_LIFECYCLE_CERTIFICATION_ROWS", "_SCORING_PLAYER_IDS", "_attached_burden_state"]
__all__ += ["_decisions_for_seeded_secondary_state", "_home_objective", "_place_unit"]
__all__ += ["_unit_by_id", "army_muster_request", "certification_unit_selections"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["default_unit_selection", "mustered_armies", "next_secondary_mission_choice_request"]
__all__ += ["phase11c_config", "phase17n_state_with_setup"]
__all__ += ["record_existing_primary_turn_start_evidence_events_for_fixture"]
__all__ += ["record_new_primary_battlefield_departure_events"]
__all__ += ["record_unresolved_when_drawn_card", "replace"]
__all__ += ["resolved_secondary_mission_selection_for_card", "secondary_mission_inventory_rows"]
__all__ += ["seed_sequential_tactical_turn_cap_conditions", "step6g_matrix_case_keys"]
__all__ += ["unit_selection", "validate_attached_rules_unit_identity_after_destruction"]
