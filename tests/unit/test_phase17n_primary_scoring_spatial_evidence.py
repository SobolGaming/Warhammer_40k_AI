from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase17n_primary_scoring_spatial_evidence import (
    _PLAYER_A_ANCHORS,
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    TABLE_QUARTER_IDS,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachmentDeclaration,
    BattlefieldRegionKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlePhase,
    DecisionController,
    DetachmentSelection,
    EventRecordPayload,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    JsonValue,
    MissionSetup,
    ModelPlacement,
    ModelProfileSelection,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    PlacedArmy,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    ReserveKind,
    ReserveState,
    RulesetDescriptor,
    TransportCapacityProfile,
    TransportCargoState,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    VictoryPointLedger,
    _authoritative_spatial_record,
    _catalog,
    _character_selection,
    _controlled_objective_record,
    _corrupt_final_model_destroyed_event,
    _corrupt_primary_recorded_event_graph,
    _corrupt_primary_turn_start_evidence,
    _event_payload,
    _infantry_selection,
    _make_unit_placement_partial,
    _mission_setup,
    _muster_request,
    _primary_historical_destruction_lifecycle_payload,
    _record_primary_scoring_evidence,
    _recorded_departure_event,
    _recorded_event_for_corruption,
    _relabel_primary_departure,
    _relocate_unit_placement,
    _run_primary_spatial_evidence_constructor_corruption,
    _run_primary_spatial_evidence_state_corruption,
    _spatial_evidence_state,
    _transport_selection,
    _unit,
    _unit_placement,
    _unit_selection,
    _with_destroyed_unit,
    build_primary_scoring_spatial_evidence,
    build_primary_scoring_state_evidence,
    deepcopy,
    math,
    mission_scoring_policies_from_setup,
    muster_army,
    objective_control_record_hash,
    primary_battlefield_departure_id,
    primary_historical_lifecycle_payload,
    pytest,
    record_new_primary_turn_start_evidence_events,
    record_primary_scoring_state_evidence,
    record_primary_turn_start_evidence,
    replace,
    reposition_destruction_policy,
    resolve_end_turn_cleanup,
    starting_attached_unit_records_for_army,
    validate_primary_victory_point_transaction,
    validate_victory_point_ledger_policy,
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("quarter_id", "quarter_id is unsupported"),
        ("unrequested_quarter", "unrequested table-quarter witnesses"),
        ("unrequested_territory", "unrequested territory witnesses"),
        ("unrequested_objectives", "unrequested territory objectives"),
        ("unsupported_condition", "requested_condition_ids are unsupported"),
        ("quarters_not_tuple", "table-quarter witnesses must be a tuple"),
        ("quarter_untyped", "table-quarter witnesses are invalid"),
        ("quarter_duplicate_unit", "rules units must have one table-quarter witness"),
        ("quarters_unsorted", "table-quarter witnesses must be sorted"),
        ("territories_not_tuple", "territory witnesses must be a tuple"),
        ("territory_untyped", "territory witnesses are invalid"),
        ("territory_duplicate_unit", "territory witness units must be unique"),
        ("territories_unsorted", "territory witnesses must be sorted"),
        ("conditions_not_tuple", "requested_condition_ids must be a tuple"),
        ("conditions_empty", "requested_condition_ids must not be empty"),
        ("conditions_duplicate", "requested_condition_ids must not contain duplicates"),
        ("conditions_unsorted", "requested_condition_ids must be sorted"),
        ("battle_round", "battle_round must be a positive integer"),
        ("timing", "timing must be ObjectiveControlTiming"),
    ],
)
def test_primary_spatial_evidence_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_spatial_evidence_constructor_corruption(corruption)


def test_primary_spatial_evidence_public_validation_fails_closed() -> None:
    state = _spatial_evidence_state()
    record = _authoritative_spatial_record(state)

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        build_primary_scoring_spatial_evidence(
            state=cast(GameState, object()),
            player_id="player-a",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="requires an ObjectiveControlRecord"):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-a",
            record=cast(ObjectiveControlRecord, object()),
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-c",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="record hash requires an ObjectiveControlRecord"):
        objective_control_record_hash(cast(ObjectiveControlRecord, object()))


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("mission_missing", "requires mission and battlefield state"),
        ("placed_unavailable", "placed model marked unavailable"),
        ("alive_unplaced", "alive rules unit with no accounted placement"),
        ("mission_player", "player_id is not in MissionSetup"),
        ("territory_missing", "exactly one territory for each player role"),
        ("dimensions", "battlefield dimensions drifted from MissionSetup"),
        ("boundary_missing", "requires an active battle boundary"),
        ("record_drift", "ObjectiveControlRecord drifted from GameState"),
        ("record_unstored", "requires the authoritative ObjectiveControlRecord"),
    ],
)
def test_primary_spatial_evidence_state_integrity_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_spatial_evidence_state_corruption(corruption)


def test_primary_spatial_evidence_is_group_aware_exact_and_deterministic() -> None:
    state = _spatial_evidence_state()
    record = _authoritative_spatial_record(state)

    first = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
    )
    second = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
    )

    assert first == second
    assert {witness.quarter_id for witness in first.table_quarter_unit_witnesses} == set(
        TABLE_QUARTER_IDS
    )
    assert {witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses} == {
        "attached-unit:army-alpha:body",
        "army-alpha:east",
        "army-alpha:south",
        "army-alpha:southeast",
    }
    attached_witness = next(
        witness
        for witness in first.table_quarter_unit_witnesses
        if witness.rules_unit_instance_id == "attached-unit:army-alpha:body"
    )
    assert len(attached_witness.model_instance_ids) == 6
    assert not {
        "army-alpha:body",
        "army-alpha:leader",
    }.intersection(witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses)
    assert tuple(
        witness.rules_unit_instance_id for witness in first.enemy_units_wholly_within_own_territory
    ) == ("army-beta:enemy",)
    assert first.opponent_territory_objective_ids == (
        "take-and-hold-vs-purge-the-foe-layout-1-central-01",
        "take-and-hold-vs-purge-the-foe-layout-1-defender-home-01",
        "take-and-hold-vs-purge-the-foe-layout-1-expansion-01",
    )
    assert first.to_payload() == second.to_payload()

    near_model = _unit(state, "army-alpha:near").own_models[0]
    assert state.battlefield_state is not None
    near_pose = state.battlefield_state.model_placement_by_id(near_model.model_instance_id).pose
    assert math.hypot(near_pose.position.x - 22.0, near_pose.position.y - 30.0) > 6.0
    assert "army-alpha:near" not in {
        witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses
    }
    assert {
        "army-alpha:reserve",
        "army-alpha:embarked",
        "army-alpha:destroyed",
    }.isdisjoint(witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses)


def test_primary_spatial_evidence_rejects_partial_alive_rules_unit_placement() -> None:
    state = _spatial_evidence_state()
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:east")
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(placement.model_placements[:-1])
    )
    record = _authoritative_spatial_record(state)

    with pytest.raises(
        GameLifecycleError,
        match="requires every alive model in a rules unit to be placed",
    ):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-a",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
        )


def test_primary_spatial_evidence_computes_only_requested_families() -> None:
    objective_state = _spatial_evidence_state()
    _make_unit_placement_partial(objective_state, unit_instance_id="army-alpha:east")
    objective_record = _authoritative_spatial_record(objective_state)

    objective_evidence = build_primary_scoring_spatial_evidence(
        state=objective_state,
        player_id="player-a",
        record=objective_record,
        requested_condition_ids=(PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,),
    )

    assert objective_evidence.opponent_territory_objective_ids
    assert objective_evidence.table_quarter_unit_witnesses == ()
    assert objective_evidence.enemy_units_wholly_within_own_territory == ()

    quarter_state = _spatial_evidence_state()
    _make_unit_placement_partial(quarter_state, unit_instance_id="army-beta:enemy")
    quarter_record = _authoritative_spatial_record(quarter_state)

    quarter_evidence = build_primary_scoring_spatial_evidence(
        state=quarter_state,
        player_id="player-a",
        record=quarter_record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )

    assert quarter_evidence.table_quarter_unit_witnesses
    assert quarter_evidence.enemy_units_wholly_within_own_territory == ()
    assert quarter_evidence.opponent_territory_objective_ids == ()

    territory_state = _spatial_evidence_state()
    _make_unit_placement_partial(territory_state, unit_instance_id="army-alpha:east")
    territory_record = _authoritative_spatial_record(territory_state)

    territory_evidence = build_primary_scoring_spatial_evidence(
        state=territory_state,
        player_id="player-a",
        record=territory_record,
        requested_condition_ids=(PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,),
    )

    assert territory_evidence.enemy_units_wholly_within_own_territory
    assert territory_evidence.table_quarter_unit_witnesses == ()
    assert territory_evidence.opponent_territory_objective_ids == ()


def test_primary_spatial_evidence_excludes_removed_wounds_alive_reserve() -> None:
    state = _spatial_evidence_state()
    assert state.battlefield_state is not None
    reserve_state = state.reserve_states[0]
    reserve_unit = _unit(state, reserve_state.unit_instance_id)
    reserve_model_ids = tuple(sorted(model.model_instance_id for model in reserve_unit.own_models))
    assert all(model.is_alive for model in reserve_unit.own_models)

    state.reserve_states = [reserve_state.mark_destroyed(battle_round=state.battle_round)]
    state.battlefield_state = state.battlefield_state.with_unplaced_models_marked_removed(
        reserve_model_ids
    )
    record = _authoritative_spatial_record(state)

    evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )

    assert set(reserve_model_ids) <= set(state.battlefield_state.removed_model_ids)
    assert reserve_unit.unit_instance_id not in {
        witness.rules_unit_instance_id for witness in evidence.table_quarter_unit_witnesses
    }


def test_primary_spatial_evidence_counts_survivors_after_coherency_cleanup() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="take-and-hold",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
            terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
            attacker_force_disposition_id="reconnaissance",
            defender_force_disposition_id="take-and-hold",
        ),
    )
    assert state.battlefield_state is not None
    east_placement = state.battlefield_state.unit_placement_by_id("army-alpha:east")
    isolated = replace(
        east_placement.model_placements[-1],
        pose=Pose.at(42.0, 57.0),
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        east_placement.with_model_placements((*east_placement.model_placements[:-1], isolated))
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    cleanup, updated_battlefield = resolve_end_turn_cleanup(
        game_id=state.game_id,
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        ),
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        battle_round=state.battle_round,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        chosen_model_instance_ids=(isolated.model_instance_id,),
    )
    state.battlefield_state = updated_battlefield
    state.end_turn_cleanup_states.append(cleanup)
    record = _authoritative_spatial_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
    )

    assert isolated.model_instance_id in state.battlefield_state.removed_model_ids
    assert next(
        model
        for model in _unit(state, "army-alpha:east").own_models
        if model.model_instance_id == isolated.model_instance_id
    ).is_alive
    evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )
    east_witness = next(
        witness
        for witness in evidence.table_quarter_unit_witnesses
        if witness.rules_unit_instance_id == "army-alpha:east"
    )
    assert east_witness.model_instance_ids == tuple(
        sorted(
            placement.model_instance_id
            for placement in east_placement.model_placements
            if placement.model_instance_id != isolated.model_instance_id
        )
    )


def test_reconnaissance_sweep_scores_exclusive_quarters_through_lifecycle() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="take-and-hold",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
            terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
            attacker_force_disposition_id="reconnaissance",
            defender_force_disposition_id="take-and-hold",
        ),
    )
    assert state.battlefield_state is not None
    leader = state.battlefield_state.unit_placement_by_id("army-alpha:leader")
    assert len(leader.model_placements) == 1
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        leader.with_model_placements((leader.model_placements[0].with_pose(Pose.at(10.3, 50.9)),))
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()

    ledger = state.victory_point_ledger_for_player("player-a")
    assert ledger.victory_points == 6
    assert len(ledger.transactions) == 1
    metadata = ledger.transactions[0].metadata
    assert isinstance(metadata, dict)
    assert metadata["scoring_rule_id"] == "reconnaissance-sweep-four-quarters-turn-end"
    assert metadata["primary_scoring_achieved_rule_ids"] == [
        "reconnaissance-sweep-four-quarters-turn-end",
        "reconnaissance-sweep-three-quarters-turn-end",
    ]
    assert metadata["primary_scoring_suppressed_rule_ids"] == [
        "reconnaissance-sweep-three-quarters-turn-end"
    ]


def test_determined_acquisition_scores_exact_opponent_territory_through_lifecycle() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="take-and-hold",
        player_b_force_disposition_id="disruption",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
            terrain_layout_id="take-and-hold-vs-disruption-layout-1",
            attacker_force_disposition_id="take-and-hold",
            defender_force_disposition_id="disruption",
        ),
    )
    state.battle_round = 2
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)

    state.advance_to_next_battle_phase()

    ledger = state.victory_point_ledger_for_player("player-a")
    assert ledger.victory_points == 15
    amounts_by_rule_id = {
        metadata["scoring_rule_id"]: transaction.amount
        for transaction in ledger.transactions
        if isinstance((metadata := transaction.metadata), dict)
    }
    assert amounts_by_rule_id == {
        "determined-acquisition-each-objective": 9,
        "determined-acquisition-opponent-territory-bonus": 6,
    }
    territory_transaction = next(
        transaction
        for transaction in ledger.transactions
        if isinstance(transaction.metadata, dict)
        and transaction.metadata["scoring_rule_id"]
        == "determined-acquisition-opponent-territory-bonus"
    )
    assert isinstance(territory_transaction.metadata, dict)
    assert territory_transaction.metadata["opponent_territory_objective_ids"] == [
        "take-and-hold-vs-disruption-layout-1-defender-home-01",
        "take-and-hold-vs-disruption-layout-1-expansion-01",
    ]
    assert territory_transaction.metadata["primary_scoring_selected_rule_ids"] == [
        "determined-acquisition-each-objective",
        "determined-acquisition-opponent-territory-bonus",
    ]


def test_search_and_scour_scores_exact_end_of_battle_territory_evidence() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 5
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    ordinary_record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
        controlled_objective_ids=(
            "reconnaissance-vs-priority-assets-layout-1-central-01",
            "reconnaissance-vs-priority-assets-layout-1-expansion-01",
            "reconnaissance-vs-priority-assets-layout-1-expansion-02",
        ),
    )
    policies = mission_scoring_policies_from_setup(setup)
    ordinary_awards = policies.primary_awards_from_objective_control(
        record=ordinary_record,
        authoritative_state=state,
    )
    assert {
        metadata["scoring_rule_id"]: award.amount
        for award in ordinary_awards
        if isinstance((metadata := award.metadata), dict)
    } == {
        "search-and-scour-central-objective-turn-end": 3,
        "search-and-scour-objective-control": 12,
    }
    _record_primary_scoring_evidence(
        state=state,
        record=ordinary_record,
        end_of_battle=False,
    )
    for ordinary_award in ordinary_awards:
        state.award_victory_points(ordinary_award)
    assert state.victory_point_total("player-a") == 15

    _relocate_unit_placement(
        state,
        unit_instance_id="army-beta:enemy",
        anchor=(32.0, 7.0),
    )
    state.turn_order = ("player-b", "player-a")
    record = ordinary_record
    required_conditions = policies.policy_for_player(
        "player-a"
    ).required_primary_spatial_conditions(
        record=record,
        end_of_battle=True,
    )
    spatial_evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=required_conditions,
    )
    state_evidence = build_primary_scoring_state_evidence(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        end_of_battle=True,
    )
    awards = policies.policy_for_player("player-a").primary_awards_from_objective_control(
        record=record,
        mission_setup=setup,
        turn_order=state.turn_order,
        turn_start_states=tuple(state.primary_objective_turn_start_states),
        terrain_trap_states=tuple(state.primary_terrain_trap_states),
        unit_destruction_states=tuple(state.primary_unit_destruction_states),
        state_evidence=state_evidence,
        spatial_evidence=spatial_evidence,
        scoring_player_ids=("player-a",),
        end_of_battle=True,
    )

    assert spatial_evidence.enemy_units_wholly_within_own_territory == ()
    assert len(awards) == 1
    award = awards[0]
    assert award.amount == 5
    assert isinstance(award.metadata, dict)
    assert award.metadata["scoring_rule_id"] == (
        "search-and-scour-no-enemy-in-territory-end-battle"
    )
    assert award.metadata["own_territory_region_id"] == (
        "reconnaissance-vs-priority-assets-layout-1-attacker-territory"
    )
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=True,
    )
    ledger = state.victory_point_ledger_for_player("player-a")
    applied_amount, transaction_metadata = policies.capped_award_for_ledger(
        ledger=ledger,
        award=award,
        objective_control_records=tuple(state.objective_control_records),
        primary_scoring_state_evidence_records=tuple(state.primary_scoring_state_evidence_records),
        turn_order=state.turn_order,
        current_active_player_id=state.active_player_id,
    )
    updated_ledger, transaction = ledger.award(
        award,
        applied_amount=applied_amount,
        metadata=transaction_metadata,
    )
    assert transaction.amount == 5
    assert transaction.scoring_timing == "end_of_battle"
    assert updated_ledger.victory_points == 20
    restored_ledger = VictoryPointLedger.from_payload(updated_ledger.to_payload())
    assert restored_ledger == updated_ledger
    validate_victory_point_ledger_policy(
        policy=policies.policy_for_player("player-a"),
        ledger=restored_ledger,
        objective_control_records=tuple(state.objective_control_records),
        primary_scoring_state_evidence_records=tuple(state.primary_scoring_state_evidence_records),
        turn_order=state.turn_order,
    )
    assert isinstance(transaction.metadata, dict)
    invalid_transaction = replace(
        transaction,
        amount=100,
        metadata={
            **transaction.metadata,
            "vp_cap_audit": {
                "requested_amount": 5,
                "applied_amount": 100,
            },
        },
    )

    with pytest.raises(GameLifecycleError, match="applied_amount exceeds requested_amount"):
        validate_primary_victory_point_transaction(
            policy=policies.policy_for_player("player-a"),
            transaction=invalid_transaction,
            objective_control_records=tuple(state.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                state.primary_scoring_state_evidence_records
            ),
            turn_order=state.turn_order,
        )


def test_primary_restore_rejects_forged_round_two_end_of_battle_exemption() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 2
    record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        controlled_objective_ids=("reconnaissance-vs-priority-assets-layout-1-expansion-01",),
    )
    policies = mission_scoring_policies_from_setup(setup)
    award = next(
        award
        for award in policies.primary_awards_from_objective_control(
            record=record,
            authoritative_state=state,
        )
        if isinstance(award.metadata, dict)
        and award.metadata["scoring_rule_id"] == "search-and-scour-objective-control"
    )
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )
    state.award_victory_points(award)
    payload = state.to_payload()
    player_ledger = next(
        ledger for ledger in payload["victory_point_ledgers"] if ledger["player_id"] == "player-a"
    )
    player_ledger["transactions"][0]["scoring_timing"] = "end_of_battle"

    with pytest.raises(GameLifecycleError, match="scoring_timing drifted from its source rule"):
        GameState.from_payload(payload)


def test_primary_restore_rejects_more_than_fifteen_ordinary_vp_in_one_round() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 5
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
        controlled_objective_ids=tuple(
            marker.objective_marker_id
            for marker in setup.objective_markers
            if "attacker-home" not in marker.objective_marker_id
        ),
    )
    policies = mission_scoring_policies_from_setup(setup)
    awards = policies.primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
    )
    assert sum(award.amount for award in awards) == 19
    ledger = VictoryPointLedger.initial(player_id="player-a")
    for award in awards:
        ledger, _ = ledger.award(award)
    state.victory_point_ledgers = [
        ledger if stored.player_id == "player-a" else stored
        for stored in state.victory_point_ledgers
    ]
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )

    with pytest.raises(
        GameLifecycleError,
        match="cap audit drifted from chronological ledger policy",
    ):
        GameState.from_payload(state.to_payload())


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        (
            "departure_state_missing",
            "Primary battlefield departure recorded event requires a state payload",
        ),
        (
            "departure_id_missing",
            "Primary battlefield departure recorded event requires a departure ID",
        ),
        (
            "departure_payload_drift",
            "Primary battlefield departure recorded-event payload drift",
        ),
        (
            "departure_duplicate",
            "Primary battlefield departure requires exactly one recorded event",
        ),
        (
            "destruction_state_missing",
            "Primary destruction recorded state is malformed",
        ),
        (
            "destruction_id_missing",
            "Primary destruction recorded identity is malformed",
        ),
        (
            "destruction_payload_drift",
            "Primary destruction recorded-event payload drift",
        ),
        (
            "destruction_duplicate",
            "Primary destruction historical state requires exactly one recorded event",
        ),
    ],
)
def test_primary_historical_restore_rejects_recorded_event_graph_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_primary_recorded_event_graph(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("attribution", "Rule destruction cause payload binding drift"),
        ("source_witness_missing", "Rule destruction cause payload binding drift"),
        ("source_witness_none", "Rule destruction cause payload binding drift"),
        ("destroyed_witness_missing", "Rule destruction cause payload binding drift"),
        ("model_malformed", "Model destruction cause consumption identity drift"),
        ("model_outside_starting_unit", "Model destruction cause consumption identity drift"),
        ("game", "Model destruction cause consumption identity drift"),
        ("battle_round", "Rule destruction cause payload binding drift"),
        ("active_player", "Rule destruction cause payload binding drift"),
        ("target", "Rule destruction cause payload binding drift"),
    ],
)
def test_primary_historical_restore_rejects_final_model_event_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_final_model_destroyed_event(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("removal_kind", "expected_error"),
    [
        (
            BattlefieldRemovalKind.TEMPORARILY_REMOVED,
            "Primary battlefield departure has no authoritative mutation provider",
        ),
        (
            BattlefieldRemovalKind.EMBARK,
            "Primary EMBARK departure requires one authoritative transport mutation event",
        ),
        (
            BattlefieldRemovalKind.INTO_RESERVES,
            "Primary INTO_RESERVES departure requires one authoritative reserve mutation event",
        ),
    ],
)
def test_primary_restore_rejects_departure_relabelled_without_route_provider(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    removal_kind: BattlefieldRemovalKind,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _relabel_primary_departure(payload=payload, removal_kind=removal_kind)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        (
            "snapshot_missing_field",
            "PrimaryRulesUnitTurnStartSnapshot payload is missing required field: source_id",
        ),
        (
            "snapshot_unexpected_field",
            "PrimaryRulesUnitTurnStartSnapshot payload contains unexpected field: forged",
        ),
        (
            "snapshot_memberships_malformed",
            "PrimaryRulesUnitTurnStartSnapshot rules_unit_memberships must be a list",
        ),
        (
            "snapshot_round_malformed",
            "PrimaryRulesUnitTurnStartSnapshot battle_round must be an integer",
        ),
        (
            "snapshot_round_zero",
            "PrimaryRulesUnitTurnStartSnapshot battle_round must be at least 1",
        ),
        (
            "objective_witness_empty",
            "PrimaryObjectiveMarkerWitness requires at least one model",
        ),
        (
            "objective_witness_unevaluated",
            "PrimaryComponentTurnStartMembership objective witness references an unevaluated model",
        ),
        (
            "evaluated_model_duplicate",
            "PrimaryComponentTurnStartMembership evaluated_model_instance_ids must not "
            "contain duplicates",
        ),
        ("snapshot_game", "PrimaryRulesUnitTurnStartSnapshot game_id drift"),
        (
            "snapshot_player",
            "PrimaryRulesUnitTurnStartSnapshot player_id is not in this game",
        ),
        ("snapshot_id", "PrimaryRulesUnitTurnStartSnapshot snapshot_id drift"),
        ("snapshot_source", "PrimaryRulesUnitTurnStartSnapshot source_id drift"),
        (
            "snapshot_duplicate",
            "GameState primary rules-unit turn-start snapshots must be unique",
        ),
        (
            "snapshot_missing_component",
            "Primary rules-unit turn-start snapshot must contain every physical unit",
        ),
        (
            "snapshot_attached_grouping",
            "Primary rules-unit turn-start snapshot has invalid attached-unit grouping",
        ),
        (
            "snapshot_attached_identity_missing",
            "Primary rules-unit turn-start snapshot must preserve its attached identity",
        ),
        (
            "snapshot_independent_grouping",
            "Primary rules-unit turn-start snapshot has invalid independent-unit grouping",
        ),
        (
            "rules_membership_duplicate",
            "PrimaryRulesUnitTurnStartSnapshot rules-unit memberships must be unique",
        ),
        (
            "component_overlap",
            "PrimaryRulesUnitTurnStartSnapshot physical components must not overlap",
        ),
        (
            "component_duplicate",
            "PrimaryRulesUnitTurnStartMembership components must be unique",
        ),
        (
            "component_empty",
            "PrimaryRulesUnitTurnStartMembership requires at least one component",
        ),
        (
            "objective_witness_duplicate",
            "PrimaryComponentTurnStartMembership objective witnesses must be unique",
        ),
        (
            "snapshot_model_outside_component",
            "Primary turn-start snapshot references a model outside its component",
        ),
        (
            "snapshot_unknown_area",
            "Primary turn-start snapshot references an unknown logical terrain area",
        ),
        (
            "snapshot_unknown_objective",
            "Primary turn-start snapshot references an unknown objective marker",
        ),
        (
            "objective_game",
            "PrimaryObjectiveTurnStartState game_id drift",
        ),
        (
            "objective_player",
            "PrimaryObjectiveTurnStartState player_id is not in this game",
        ),
        ("objective_state_id", "PrimaryObjectiveTurnStartState state_id drift"),
        ("objective_source", "PrimaryObjectiveTurnStartState source_id drift"),
        (
            "objective_unknown_marker",
            "PrimaryObjectiveTurnStartState contains an unknown objective marker",
        ),
        (
            "objective_duplicate",
            "GameState primary turn-start states must be unique",
        ),
        (
            "turn_graph_missing_objective",
            "Primary turn-start objective and position evidence turn keys must match exactly",
        ),
        (
            "destruction_missing_snapshot",
            "Primary unit destruction requires exactly one matching turn-start position snapshot",
        ),
        (
            "destruction_terrain_drift",
            "Primary unit destruction terrain evidence does not match its turn snapshot",
        ),
        (
            "destruction_objective_drift",
            "Primary unit destruction objective evidence does not match its turn snapshot",
        ),
    ],
)
def test_primary_restore_rejects_turn_start_evidence_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_primary_turn_start_evidence(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


__all__: list[str] = []
__all__ += ["Any", "ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "AttachmentDeclaration"]
__all__ += ["BattlefieldRegionKind", "BattlefieldRuntimeState", "DecisionController"]
__all__ += ["DetachmentSelection", "EventRecordPayload", "GameLifecycleStage", "JsonValue"]
__all__ += ["MissionSetup", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT"]
__all__ += ["PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT", "PlacedArmy"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryScoringSpatialEvidence"]
__all__ += ["PrimaryTableQuarterUnitWitness", "PrimaryTerritoryUnitWitness", "ReserveKind"]
__all__ += ["ReserveState", "RulesetDescriptor", "TransportCapacityProfile"]
__all__ += ["TransportCargoState", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["_PLAYER_A_ANCHORS", "_catalog", "_character_selection", "_event_payload"]
__all__ += ["_infantry_selection", "_muster_request"]
__all__ += ["_primary_historical_destruction_lifecycle_payload", "_recorded_departure_event"]
__all__ += ["_recorded_event_for_corruption", "_transport_selection", "_unit_placement"]
__all__ += ["_unit_selection", "_with_destroyed_unit", "muster_army"]
__all__ += ["primary_battlefield_departure_id", "primary_historical_lifecycle_payload"]
__all__ += ["record_new_primary_turn_start_evidence_events"]
__all__ += ["record_primary_scoring_state_evidence", "record_primary_turn_start_evidence"]
__all__ += ["reposition_destruction_policy", "starting_attached_unit_records_for_army"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
