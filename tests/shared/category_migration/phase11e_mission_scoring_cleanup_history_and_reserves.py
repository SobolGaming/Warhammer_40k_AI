from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    ArmyDefinition,
    AttackSequence,
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlePhase,
    BattleRoundFlow,
    DamageProfile,
    DecisionRecord,
    DestructionSourceKind,
    DiceRollManager,
    EventLog,
    EventRecord,
    GameLifecycle,
    GameLifecyclePayload,
    GameState,
    JsonValue,
    MissionSetup,
    ModelDestructionAttribution,
    ModelRemovalRecord,
    PlaceholderPhaseHandler,
    PrimaryBattlefieldDepartureState,
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionState,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    RulesUnitObjectiveProximityWitness,
    SaveKind,
    ShootingPhaseState,
    TransportCapacityProfile,
    TransportCargoState,
    UnitInstance,
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    cast,
    historical_event_integrity,
    json,
    mission_scoring_policies_from_setup,
    primary_battlefield_departure_id,
    pytest,
    record_primary_destroyed_model_departures,
    record_primary_turn_start_evidence,
    record_primary_unit_destructions_for_destroyed_models,
    record_secondary_destruction_for_fixture,
    record_shooting_declaration_for_executor_fixture,
    replace,
    reserve_destruction_policy_from_scoring_policy,
    resolve_attack_sequence_until_blocked,
    rules_unit_objective_proximity_witness,
    rules_unit_view_by_id,
    saving_throw_roll_spec,
    seed_completed_fight_phase,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_configuration import (
    _battle_state,
    _battle_state_from_config,
    _config_with_player_a_attached_unit,
    _config_with_player_a_transport,
    _config_with_player_b_character,
    _event_companion_meatgrinder_mission_setup,
    _mission_setup,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_mission_lifecycle import (
    _battle_lifecycle,
    _record_missing_turn_start_evidence_events,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_state_primitives import (
    _place_unit_near_point,
)


@pytest.fixture(scope="module")
def authentic_primary_destruction_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_primary_destruction_lifecycle_payload()


@pytest.fixture(scope="module")
def authentic_reserve_deadline_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_reserve_deadline_lifecycle_payload()


@pytest.fixture(scope="module")
def authentic_attached_unit_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_attached_unit_lifecycle_payload()


def _battle_state_with_unarrived_reserve_at_round_three_deadline() -> tuple[GameState, str]:
    state = _battle_state()
    assert state.battlefield_state is not None
    reserve_unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                mission_scoring_policies_from_setup(_mission_setup()).policy_for_player("player-a")
            ),
        )
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    seed_completed_fight_phase(state)
    record_primary_turn_start_evidence(state=state)
    return state, reserve_unit.unit_instance_id


def _remove_unit_for_primary_destruction(
    state: GameState,
    *,
    unit_instance_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(unit.own_model_ids())
    )


def _record_test_primary_unit_destruction(
    state: GameState,
    *,
    destroying_player_id: str,
    destroyed_unit_instance_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState:
    attribution, witness = _test_primary_destruction_attribution(
        state,
        destroying_player_id=destroying_player_id,
    )
    destroyed_unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == destroyed_unit_instance_id
    )
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=destroyed_unit.own_model_ids(),
        source_id=source_id,
    )
    return state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=f"{source_id}:model-destroyed-event",
        source_rules_unit_objective_proximity_witness=witness,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        source_id=source_id,
    )


def _authentic_primary_destruction_lifecycle_payload() -> GameLifecyclePayload:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:intercessor-unit-1"
    )
    defender = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-beta:character-unit-3"
    )
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.current_wounds),
    )
    state.replace_shooting_phase_state(
        ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
            selected_unit_ids=(attacker.unit_instance_id,),
            shot_unit_ids=(attacker.unit_instance_id,),
        )
    )
    sequence_id = "attack-sequence:phase17n-destruction-integrity-runtime-attack"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    record_shooting_declaration_for_executor_fixture(
        state=state,
        decisions=lifecycle.decision_controller,
        sequence=sequence,
        result_id=sequence_id.removeprefix("attack-sequence:"),
    )
    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    assert remaining is None
    assert attack_status is None
    BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        }
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert len(state.primary_unit_destruction_states) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _transport_reserve_deadline_lifecycle(
    *,
    preexisting_cargo_casualty: bool = False,
    destruction_deadline_policy: ReserveDestructionTimingPolicy | None = None,
) -> tuple[GameLifecycle, TransportCargoState, tuple[str, ...]]:
    config = _config_with_player_a_transport()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
        )
    )
    state = cast(GameState, lifecycle.state)
    assert state.battlefield_state is not None
    owner_army = state.army_definition_for_player("player-a")
    assert owner_army is not None
    transport = owner_army.unit_by_id("army-alpha:transport-unit-2")
    passenger = owner_army.unit_by_id("army-alpha:intercessor-unit-1")
    route_model_ids = tuple(
        sorted(
            model.model_instance_id for unit in (transport, passenger) for model in unit.own_models
        )
    )
    battlefield = state.battlefield_state
    if preexisting_cargo_casualty:
        casualty_id = passenger.own_models[0].model_instance_id
        _set_model_wounds_remaining(
            state,
            model_instance_id=casualty_id,
            wounds_remaining=0,
        )
        battlefield = battlefield.with_removed_models((casualty_id,))
    state.replace_battlefield_state(
        battlefield.without_unit_placement(passenger.unit_instance_id).without_unit_placement(
            transport.unit_instance_id
        )
    )
    cargo_state = TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=("INFANTRY",),
            source_id="phase17n-reserve-deadline-transport-capacity",
        ),
        embarked_unit_instance_ids=(passenger.unit_instance_id,),
    )
    state.record_transport_cargo_state(cargo_state)
    resolved_policy = destruction_deadline_policy
    if resolved_policy is None:
        assert state.mission_setup is not None
        resolved_policy = reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
        )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=transport.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=resolved_policy,
        embarked_unit_instance_ids=(passenger.unit_instance_id,),
    )
    state.record_reserve_state(declared_reserve)
    lifecycle.decision_controller.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    return lifecycle, cargo_state, route_model_ids


def _resolve_transport_reserve_at_round_boundary(lifecycle: GameLifecycle) -> None:
    state = cast(GameState, lifecycle.state)
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    seed_completed_fight_phase(state)
    record_primary_turn_start_evidence(state=state)
    BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT)}
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )


def _authentic_reserve_deadline_lifecycle_payload() -> GameLifecyclePayload:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    reserve_unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(reserve_unit.unit_instance_id)
    )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(
                cast(MissionSetup, state.mission_setup)
            ).policy_for_player("player-a")
        ),
    )
    state.record_reserve_state(declared_reserve)
    lifecycle.decision_controller.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    seed_completed_fight_phase(state)
    record_primary_turn_start_evidence(state=state)
    BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT)}
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    reserve_destructions = tuple(
        destruction
        for destruction in state.primary_unit_destruction_states
        if destruction.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
    )
    assert len(reserve_destructions) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _authentic_attached_unit_lifecycle_payload() -> GameLifecyclePayload:
    config = _config_with_player_a_attached_unit()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
        coherent_attached_units=True,
    )
    state = lifecycle.state
    assert state is not None
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert len(state.starting_attached_unit_records) == 1
    assert not state.primary_unit_destruction_states
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _authentic_integrity_graph(
    payload: GameLifecyclePayload,
) -> tuple[GameState, tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    restored = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(payload, sort_keys=True)),
        )
    )
    state = restored.state
    assert state is not None
    return (
        state,
        restored.decision_controller.event_log.records,
        restored.decision_controller.records,
    )


def _authentic_timeline_graph(
    payload: GameLifecyclePayload,
) -> tuple[
    GameState,
    tuple[PrimaryUnitDestructionState, ...],
    tuple[PrimaryBattlefieldDepartureState, ...],
    dict[str, historical_event_integrity._DestroyedDepartureSource],  # pyright: ignore[reportPrivateUsage]
    tuple[EventRecord, ...],
    dict[str, int],
    dict[str, historical_event_integrity._ScoringRulesUnitIdentity],  # pyright: ignore[reportPrivateUsage]
    tuple[DecisionRecord, ...],
]:
    state, event_records, decision_records = _authentic_integrity_graph(payload)
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(sorted(unit.own_model_ids()))
        for army in state.army_definitions
        for unit in army.units
    }
    rules_unit_components_by_id = historical_event_integrity._rules_unit_components_by_id(  # pyright: ignore[reportPrivateUsage]
        state=state
    )
    identities_by_id = historical_event_integrity._scoring_identities_by_id(  # pyright: ignore[reportPrivateUsage]
        state=state,
        model_ids_by_unit_id=model_ids_by_unit_id,
    )
    events_by_id = {event.event_id: event for event in event_records}
    event_index_by_id = _historical_event_index(event_records)
    destructions = tuple(state.primary_unit_destruction_states)
    departures = tuple(state.primary_battlefield_departure_states)
    departure_sources = historical_event_integrity._validate_destroyed_departure_provenance(  # pyright: ignore[reportPrivateUsage]
        state=state,
        destructions=destructions,
        departures=departures,
        identities_by_id=identities_by_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=rules_unit_components_by_id,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
        decision_records=decision_records,
    )
    return (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    )


def _historical_event_index(records: tuple[EventRecord, ...]) -> dict[str, int]:
    return {record.event_id: index for index, record in enumerate(records)}


def _resequence_historical_events(records: tuple[EventRecord, ...]) -> tuple[EventRecord, ...]:
    return tuple(
        replace(record, event_id=f"event-{index:06d}")
        for index, record in enumerate(records, start=1)
    )


def _unattributed_timeline_destruction(
    destruction: PrimaryUnitDestructionState,
    *,
    cause: PrimaryUnattributedDestructionCause,
    mutation_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState:
    return replace(
        destruction,
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        unattributed_cause=cause,
        source_mutation_id=mutation_id,
        source_id=source_id,
    )


def _replace_historical_event(
    records: tuple[EventRecord, ...],
    *,
    original: EventRecord,
    payload: JsonValue,
) -> tuple[EventRecord, ...]:
    return tuple(
        replace(record, payload=payload) if record.event_id == original.event_id else record
        for record in records
    )


def _typed_primary_reserve_entry_evidence() -> tuple[
    PrimaryReserveEntryProvider,
    ReserveState,
    PrimaryBattlefieldDepartureState,
    BattlefieldTransitionBatch,
]:
    unit_id = "army-alpha:intercessor-unit-1"
    model_id = f"{unit_id}:model-001"
    provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.TURN_END_ABILITY,
        provider_id="phase17n:typed-reserve-entry-provider",
        player_id="player-a",
        source_rule_id="phase17n:typed-reserve-entry-rule",
        target_rules_unit_instance_id=unit_id,
        decision_record_id="phase17n:typed-reserve-entry-decision-record",
        decision_request_id="phase17n:typed-reserve-entry-decision-request",
        decision_result_id="phase17n:typed-reserve-entry-decision-result",
        stratagem_use_id=None,
        source_terminal_event_type="phase17n:typed-reserve-entry-terminal",
    )
    reserve_state = ReserveState.entered_during_battle(
        player_id=provider.player_id,
        unit_instance_id=unit_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=2,
        phase=BattlePhase.FIGHT,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        source_rule_ids=(provider.source_rule_id,),
    )
    affected_component_ids = (unit_id,)
    departed_component_ids: tuple[str, ...] = ()
    removed_model_ids = (model_id,)
    departure_id = primary_battlefield_departure_id(
        game_id="phase11e-game",
        rules_unit_instance_id=unit_id,
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=2,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
        occurrence_id=provider.occurrence_id,
        source_id=provider.occurrence_id,
    )
    departure = PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id="phase11e-game",
        owner_player_id=provider.player_id,
        rules_unit_instance_id=unit_id,
        component_unit_instance_ids=(unit_id,),
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=2,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
        occurrence_id=provider.occurrence_id,
        source_id=provider.occurrence_id,
    )
    transition_batch = BattlefieldTransitionBatch(
        removals=(
            ModelRemovalRecord(
                model_instance_id=model_id,
                removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
                source_phase=BattlePhase.FIGHT.value,
                source_rule_id=provider.source_rule_id,
            ),
        )
    )
    return provider, reserve_state, departure, transition_batch


def _record_test_completed_primary_unit_destruction(
    state: GameState,
    *,
    destroyed_model_instance_ids: tuple[str, ...],
    destroying_player_id: str | None,
    source_id: str,
    left_battlefield: bool = True,
) -> tuple[PrimaryUnitDestructionState, ...]:
    if destroying_player_id is None:
        attribution = None
        event_id = None
        source_witness = None
        cause = PrimaryUnattributedDestructionCause.UNIT_COHERENCY
        source_mutation_id = source_id
    else:
        attribution, source_witness = _test_primary_destruction_attribution(
            state,
            destroying_player_id=destroying_player_id,
        )
        event_id = f"{source_id}:model-destroyed-event"
        cause = None
        source_mutation_id = None
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=destroyed_model_instance_ids,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=event_id,
        source_rules_unit_objective_proximity_witness=source_witness,
        destroyed_rules_unit_objective_proximity_witness=None,
        unattributed_cause=cause,
        source_mutation_id=source_mutation_id,
        left_battlefield=left_battlefield,
        source_id=source_id,
    )


def _test_primary_destruction_attribution(
    state: GameState,
    *,
    destroying_player_id: str,
) -> tuple[ModelDestructionAttribution, RulesUnitObjectiveProximityWitness]:
    source_army = next(
        army for army in state.army_definitions if army.player_id == destroying_player_id
    )
    source_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_army.units[0].unit_instance_id,
    ).unit_instance_id
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id=None,
    )
    return (
        attribution,
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=source_rules_unit_id,
        ),
    )


def _set_unit_wounds_remaining(
    state: GameState,
    *,
    unit_instance_id: str,
    wounds_remaining: int,
) -> None:
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        unit,
                        own_models=tuple(
                            replace(model, wounds_remaining=wounds_remaining)
                            for model in unit.own_models
                        ),
                    )
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )


def _set_model_wounds_remaining(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    matched = False
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models = tuple(
                replace(model, wounds_remaining=wounds_remaining)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            if updated_models != unit.own_models:
                matched = True
                updated_units.append(replace(unit, own_models=updated_models))
            else:
                updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not matched:
        raise AssertionError(f"Missing model {model_instance_id}.")
    state.replace_army_definitions(updated_armies)


def _record_secondary_vehicle_destruction(
    state: GameState,
    destroyed_unit_instance_id: str,
    *,
    started_turn_objective_marker_ids: tuple[str, ...] = (),
    event_log: EventLog | None = None,
) -> None:
    _record_secondary_unit_destruction(
        state,
        destroyed_unit_instance_id,
        started_turn_objective_marker_ids=started_turn_objective_marker_ids,
        event_log=event_log,
    )


def _record_secondary_unit_destruction(
    state: GameState,
    destroyed_unit_instance_id: str,
    *,
    started_turn_objective_marker_ids: tuple[str, ...] = (),
    event_log: EventLog | None = None,
) -> None:
    if started_turn_objective_marker_ids:
        if state.mission_setup is None:
            raise AssertionError("Secondary destruction fixture requires MissionSetup.")
        marker = next(
            marker
            for marker in state.mission_setup.objective_markers
            if marker.objective_marker_id == started_turn_objective_marker_ids[0]
        )
        _place_unit_near_point(
            state,
            unit_instance_id=destroyed_unit_instance_id,
            x_inches=marker.x_inches,
            y_inches=marker.y_inches,
        )
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        source_id=f"phase16:{destroyed_unit_instance_id}:destroyed",
        event_log=event_log,
        expected_started_turn_objective_marker_ids=started_turn_objective_marker_ids,
    )


__all__: list[str] = []
__all__ += ["ArmyDefinition", "AttackSequence", "BattlePhase", "BattleRoundFlow"]
__all__ += ["BattlefieldRemovalKind", "BattlefieldTransitionBatch", "DamageProfile"]
__all__ += ["DecisionRecord", "DestructionSourceKind", "DiceRollManager", "EventLog"]
__all__ += ["EventRecord", "GameLifecycle", "GameLifecyclePayload", "GameState", "JsonValue"]
__all__ += ["MissionSetup", "ModelDestructionAttribution", "ModelRemovalRecord"]
__all__ += ["PlaceholderPhaseHandler", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryReserveEntryProvider", "PrimaryReserveEntryProviderKind"]
__all__ += ["PrimaryUnattributedDestructionCause", "PrimaryUnitDestructionState"]
__all__ += ["ReserveDestructionTimingPolicy", "ReserveKind", "ReserveOrigin", "ReserveState"]
__all__ += ["RulesUnitObjectiveProximityWitness", "SaveKind", "ShootingPhaseState"]
__all__ += ["TransportCapacityProfile", "TransportCargoState", "UnitInstance"]
__all__ += ["_attack_pool_for_test", "_authentic_attached_unit_lifecycle_payload"]
__all__ += ["_authentic_integrity_graph", "_authentic_primary_destruction_lifecycle_payload"]
__all__ += ["_authentic_reserve_deadline_lifecycle_payload", "_authentic_timeline_graph"]
__all__ += ["_battle_lifecycle", "_battle_state", "_battle_state_from_config"]
__all__ += ["_battle_state_with_unarrived_reserve_at_round_three_deadline"]
__all__ += ["_config_with_player_a_attached_unit", "_config_with_player_a_transport"]
__all__ += ["_config_with_player_b_character", "_event_companion_meatgrinder_mission_setup"]
__all__ += ["_first_weapon_profile", "_fixed_roll_result", "_historical_event_index"]
__all__ += ["_mission_setup", "_place_unit_near_point"]
__all__ += ["_record_missing_turn_start_evidence_events", "_record_secondary_unit_destruction"]
__all__ += ["_record_secondary_vehicle_destruction"]
__all__ += ["_record_test_completed_primary_unit_destruction"]
__all__ += ["_record_test_primary_unit_destruction", "_remove_unit_for_primary_destruction"]
__all__ += ["_replace_historical_event", "_resequence_historical_events"]
__all__ += ["_resolve_transport_reserve_at_round_boundary", "_set_model_wounds_remaining"]
__all__ += ["_set_unit_wounds_remaining", "_test_primary_destruction_attribution"]
__all__ += ["_transport_reserve_deadline_lifecycle", "_typed_primary_reserve_entry_evidence"]
__all__ += ["_unattributed_timeline_destruction", "attack_sequence_hit_roll_spec"]
__all__ += ["attack_sequence_wound_roll_spec", "authentic_attached_unit_lifecycle_payload"]
__all__ += ["authentic_primary_destruction_lifecycle_payload"]
__all__ += ["authentic_reserve_deadline_lifecycle_payload", "cast", "historical_event_integrity"]
__all__ += ["json", "mission_scoring_policies_from_setup", "primary_battlefield_departure_id"]
__all__ += ["pytest", "record_primary_destroyed_model_departures"]
__all__ += ["record_primary_turn_start_evidence"]
__all__ += ["record_primary_unit_destructions_for_destroyed_models"]
__all__ += ["record_secondary_destruction_for_fixture"]
__all__ += ["record_shooting_declaration_for_executor_fixture", "replace"]
__all__ += ["reserve_destruction_policy_from_scoring_policy"]
__all__ += ["resolve_attack_sequence_until_blocked", "rules_unit_objective_proximity_witness"]
__all__ += ["rules_unit_view_by_id", "saving_throw_roll_spec", "seed_completed_fight_phase"]
