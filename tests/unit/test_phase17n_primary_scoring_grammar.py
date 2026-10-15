from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_primary_scoring_grammar import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    BattlefieldRuntimeState,
    DestructionSourceKind,
    EndTurnCleanupState,
    EventLog,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    MissionPackError,
    MissionScoringPolicies,
    MissionScoringPolicy,
    MissionScoringResolutionMode,
    MissionScoringRuleDefinition,
    MissionSetup,
    ModelDestructionAttribution,
    ModelPlacement,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerModelWitness,
    PlayerPrimaryMissionAssignment,
    Pose,
    PrimaryComponentTurnStartMembership,
    PrimaryMissionDefinition,
    PrimaryMissionProgressState,
    PrimaryMissionScoringRule,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryScoringBoundaryKind,
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    PrimaryScoringStateEvidence,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionState,
    ResolvedPrimaryScoringCandidate,
    RulesetDescriptor,
    RulesUnitObjectiveProximityWitness,
    UnitInstance,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _attributed_destruction_state,
    _build_tracking_destruction,
    _candidate,
    _catalog_tracking_state,
    _deadly_demise_attribution,
    _evidence_model_placement,
    _minimal_evidence_game_state,
    _record_tracking_destruction_models,
    _runtime_policy,
    _runtime_rule,
    _source_objective_witness,
    _source_primary_mission,
    _source_rule,
    _test_primary_state_evidence,
    _turn_start_component,
    _turn_start_snapshot,
    _unattributed_destruction_state,
    _validate_destruction_states,
    _validate_turn_start_snapshots,
    attached_selected_to_fight_risk_fixture,
    battle_state_with_army,
    bloodcrushers_army,
    bloodcrushers_battlefield_state,
    bloodcrushers_package,
    bloodcrushers_unit,
    build_primary_rules_unit_turn_start_snapshot,
    build_primary_unit_destruction_state,
    chapter_approved_2026_27_mission_pack,
    current_primary_component_turn_start_membership,
    current_primary_rules_unit_turn_start_membership,
    destruction_source_objective_proximity_witness,
    objective_control_record_hash,
    primary_rules_unit_turn_start_membership_for_lineage,
    primary_rules_unit_turn_start_snapshots_from_payload,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
    primary_scoring_resolution_mode_from_token,
    primary_scoring_timing_applies,
    primary_unit_destruction_id,
    pytest,
    record_primary_destroyed_model_departures,
    record_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
    record_primary_unit_destructions_for_destroyed_models,
    record_primary_unit_destructions_for_end_turn_cleanup,
    replace,
    resolve_primary_scoring_candidates,
    rules_unit_objective_proximity_witness,
    validate_primary_objective_turn_start_states,
    validate_primary_rules_unit_turn_start_snapshots,
    validate_primary_unit_destruction_source_witness_identity,
    validate_primary_unit_destruction_states,
    validate_primary_unit_destruction_turn_start_evidence,
    validate_victory_point_ledger_policy,
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.parametrize(
    ("timing", "battle_round", "phase", "boundary", "end_of_battle"),
    [
        (
            "battle_round_four_onwards_turn_end",
            4,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "battle_rounds_two_and_three_command_phase",
            2,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "command_phase",
            3,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "command_phase_or_round_five_turn_end",
            3,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "end_of_battle",
            5,
            "fight",
            ObjectiveControlTiming.TURN_END,
            True,
        ),
        (
            "first_and_second_battle_round_turn_end",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "first_battle_round_turn_end",
            1,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "turn_end_from_battle_round_two",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
    ],
)
def test_phase17n_every_primary_scoring_timing_has_an_executable_boundary(
    timing: str,
    battle_round: int,
    phase: str,
    boundary: ObjectiveControlTiming,
    end_of_battle: bool,
) -> None:
    assert set(SUPPORTED_PRIMARY_SCORING_TIMINGS) == {
        "battle_round_four_onwards_turn_end",
        "battle_rounds_two_and_three_command_phase",
        "command_phase",
        "command_phase_or_round_five_turn_end",
        "end_of_battle",
        "first_and_second_battle_round_turn_end",
        "first_battle_round_turn_end",
        "turn_end",
        "turn_end_from_battle_round_two",
    }
    assert primary_scoring_timing_applies(
        timing=timing,
        battle_round=battle_round,
        phase=phase,
        objective_control_timing=boundary,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=end_of_battle,
    )


@pytest.mark.parametrize(
    ("timing", "battle_round", "phase", "boundary"),
    [
        (
            "battle_round_four_onwards_turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        (
            "battle_rounds_two_and_three_command_phase",
            4,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        ("command_phase", 3, "movement", ObjectiveControlTiming.PHASE_END),
        (
            "command_phase_or_round_five_turn_end",
            5,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        (
            "command_phase_or_round_five_turn_end",
            1,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        (
            "first_and_second_battle_round_turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        (
            "first_battle_round_turn_end",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        ("turn_end", 3, "fight", ObjectiveControlTiming.PHASE_END),
        (
            "turn_end_from_battle_round_two",
            1,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
    ],
)
def test_phase17n_primary_scoring_timing_rejects_wrong_boundaries(
    timing: str,
    battle_round: int,
    phase: str,
    boundary: ObjectiveControlTiming,
) -> None:
    assert not primary_scoring_timing_applies(
        timing=timing,
        battle_round=battle_round,
        phase=phase,
        objective_control_timing=boundary,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_primary_scoring_timing_rejects_forged_boundary_context() -> None:
    with pytest.raises(GameLifecycleError, match="TURN_END boundary must be a Fight phase"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=3,
            phase="command",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="final battle-round TURN_END boundary"):
        primary_scoring_timing_applies(
            timing="end_of_battle",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="final battle-round TURN_END boundary"):
        primary_scoring_timing_applies(
            timing="end_of_battle",
            battle_round=5,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.PHASE_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="requires a five-battle-round game"):
        primary_scoring_timing_applies(
            timing="command_phase_or_round_five_turn_end",
            battle_round=3,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=3,
            end_of_battle=False,
        )


def test_phase17n_round_five_command_or_turn_end_timing_uses_turn_end_only() -> None:
    assert primary_scoring_timing_applies(
        timing="command_phase_or_round_five_turn_end",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_end_of_battle_is_an_exclusive_timing_context() -> None:
    assert not primary_scoring_timing_applies(
        timing="turn_end",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=True,
    )
    assert not primary_scoring_timing_applies(
        timing="end_of_battle",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_primary_scoring_timing_fails_closed_for_unknown_or_invalid_context() -> None:
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring rule timing"):
        primary_scoring_timing_applies(
            timing="invented_timing",
            battle_round=1,
            phase="command",
            objective_control_timing=ObjectiveControlTiming.PHASE_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="outside the battle"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=6,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="must be ObjectiveControlTiming"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing="turn_end",  # type: ignore[arg-type]
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="must be a positive integer"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=0,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="end_of_battle must be a bool"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=cast(bool, 0),
        )


def test_phase17n_primary_resolution_typed_contract_fails_closed() -> None:
    candidate = _candidate(rule_id="rule-a", amount=1)

    with pytest.raises(GameLifecycleError, match="amount must be a positive integer"):
        _candidate(rule_id="zero-amount", amount=0)
    with pytest.raises(GameLifecycleError, match="mode token must be a string"):
        primary_scoring_resolution_mode_from_token(None)
    with pytest.raises(GameLifecycleError, match="candidates must be a tuple"):
        resolve_primary_scoring_candidates(
            cast(tuple[PrimaryScoringResolutionCandidate, ...], [candidate])
        )
    with pytest.raises(GameLifecycleError, match="requires typed candidates"):
        resolve_primary_scoring_candidates(
            cast(tuple[PrimaryScoringResolutionCandidate, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="requires a typed candidate"):
        ResolvedPrimaryScoringCandidate(
            candidate=cast(PrimaryScoringResolutionCandidate, object()),
            achieved_rule_ids=("rule-a",),
            selected_rule_ids=("rule-a",),
            suppressed_rule_ids=(),
        )


def test_phase17n_objective_proximity_requires_authoritative_domain_inputs() -> None:
    state = _minimal_evidence_game_state()
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()

    with pytest.raises(GameLifecycleError, match="evidence requires GameState"):
        rules_unit_objective_proximity_witness(
            state=cast(GameState, object()),
            rules_unit_instance_id="army-source:unit-source",
        )
    with pytest.raises(GameLifecycleError, match="evidence requires EventLog"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=cast(EventLog, object()),
            attribution=attribution,
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="requires typed attribution"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=EventLog(),
            attribution=cast(ModelDestructionAttribution, object()),
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="requires its source model identity"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=EventLog(),
            attribution=_deadly_demise_attribution(source_model_instance_id=None),
            destroyed_model_placement=placement,
        )


def test_phase17n_deadly_demise_objective_evidence_inherits_exact_event_witness() -> None:
    state = _minimal_evidence_game_state()
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()
    witness = _source_objective_witness()

    missing_witness_log = EventLog()
    missing_witness_log.append(
        "model_destroyed",
        {"model_instance_id": placement.model_instance_id},
    )
    with pytest.raises(GameLifecycleError, match="lacks objective proximity evidence"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=missing_witness_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )

    inherited_log = EventLog()
    inherited_log.append(
        "model_destroyed",
        {
            "model_instance_id": placement.model_instance_id,
            "destroyed_rules_unit_objective_proximity_witness": witness.to_payload(),
        },
    )
    assert (
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=inherited_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )
        == witness
    )

    drifted_witness = replace(witness, rules_unit_instance_id="army-source:unit-other")
    drifted_log = EventLog()
    drifted_log.append(
        "model_destroyed",
        {
            "model_instance_id": placement.model_instance_id,
            "destroyed_rules_unit_objective_proximity_witness": drifted_witness.to_payload(),
        },
    )
    with pytest.raises(GameLifecycleError, match="source identity drift"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=drifted_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )


def test_phase17n_deadly_demise_requires_live_or_historical_source_placement() -> None:
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()

    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        destruction_source_objective_proximity_witness(
            state=_minimal_evidence_game_state(),
            event_log=EventLog(),
            attribution=attribution,
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="either an inherited source destruction witness"):
        destruction_source_objective_proximity_witness(
            state=_minimal_evidence_game_state(
                battlefield=BattlefieldRuntimeState(
                    battlefield_id="evidence-battlefield",
                    battlefield_width_inches=60.0,
                    battlefield_depth_inches=44.0,
                    placed_armies=(),
                )
            ),
            event_log=EventLog(),
            attribution=attribution,
            destroyed_model_placement=placement,
        )


def test_phase17n_catalog_objective_evidence_rejects_invalid_destroyed_model_context() -> None:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    state.mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id=army.player_id,
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-opponent",
        defender_force_disposition_id="purge-the-foe",
    )

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
        )
    state.battlefield_state = battlefield

    with pytest.raises(GameLifecycleError, match="must be a ModelPlacement"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=cast(ModelPlacement, object()),
        )
    outside_placement = ModelPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=f"{unit.unit_instance_id}:outside-model",
        pose=Pose.at(12.0, 12.0),
    )
    with pytest.raises(GameLifecycleError, match="outside the rules unit"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=outside_placement,
        )
    known_model = unit.own_models[0]
    drifted_component_id = known_model.model_instance_id.rsplit(":", maxsplit=1)[0]
    assert drifted_component_id != unit.unit_instance_id
    component_drift_placement = ModelPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=drifted_component_id,
        model_instance_id=known_model.model_instance_id,
        pose=Pose.at(12.0, 12.0),
    )
    with pytest.raises(GameLifecycleError, match="component identity drift"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=component_drift_placement,
        )


def test_phase17n_objective_evidence_requires_canonical_attached_rules_unit_id() -> None:
    state, _runtime, _controller, bodyguard, _leader, _enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture()
    )

    with pytest.raises(GameLifecycleError, match="canonical rules-unit identity"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=bodyguard.unit_instance_id,
        )


@pytest.mark.parametrize("retained_evidence", ["objective", "position"])
def test_turn_start_partial_evidence_rejects_before_modifier_choice(
    retained_evidence: str,
) -> None:
    from tests.order93_nonattack_helpers import add_nonattack_effects

    from warhammer40k_core.engine.decision_controller import DecisionController

    state, unit = _catalog_tracking_state()
    assert state.mission_setup is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    marker = state.mission_setup.objective_markers[0]
    placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = battlefield.with_unit_placement(
        replace(
            placement,
            model_placements=tuple(
                replace(
                    model,
                    pose=Pose.at(marker.x_inches + 2 + index * 3, marker.y_inches),
                )
                for index, model in enumerate(placement.model_placements)
            ),
        )
    )
    record_primary_turn_start_evidence(state=state)
    add_nonattack_effects(
        state,
        unit_id=unit.unit_instance_id,
        owner=state.army_definitions[0].player_id,
        characteristic="objective_control",
    )
    if retained_evidence == "objective":
        state.primary_rules_unit_turn_start_snapshots.clear()
    else:
        state.primary_objective_turn_start_states.clear()
    decisions = DecisionController()
    before_state, before_decisions = state.to_payload(), decisions.to_payload()
    with pytest.raises(GameLifecycleError, match=f"{retained_evidence} evidence already exists"):
        record_primary_turn_start_evidence(state=state, decisions=decisions)
    assert state.to_payload() == before_state
    assert decisions.to_payload() == before_decisions

    state.primary_rules_unit_turn_start_snapshots.clear()
    state.primary_objective_turn_start_states.clear()
    status = record_primary_turn_start_evidence(state=state, decisions=decisions)
    assert status is not None
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_modifier_ignores"


__all__: list[str] = []
__all__ += ["DestructionSourceKind", "EndTurnCleanupState", "GameLifecycleStage"]
__all__ += ["MissionPackError", "MissionScoringPolicies", "MissionScoringPolicy"]
__all__ += ["MissionScoringResolutionMode", "MissionScoringRuleDefinition"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveControlStatus"]
__all__ += ["ObjectiveMarkerModelWitness", "PlayerPrimaryMissionAssignment"]
__all__ += ["PrimaryComponentTurnStartMembership", "PrimaryMissionDefinition"]
__all__ += ["PrimaryMissionProgressState", "PrimaryMissionScoringRule"]
__all__ += ["PrimaryObjectiveMarkerWitness", "PrimaryRulesUnitTurnStartMembership"]
__all__ += ["PrimaryRulesUnitTurnStartSnapshot", "PrimaryScoringBoundaryKind"]
__all__ += ["PrimaryScoringResolutionMode", "PrimaryScoringStateEvidence"]
__all__ += ["PrimaryUnattributedDestructionCause", "PrimaryUnitDestructionState"]
__all__ += ["RulesUnitObjectiveProximityWitness", "RulesetDescriptor", "UnitInstance"]
__all__ += ["VictoryPointAward", "VictoryPointLedger", "VictoryPointSourceKind"]
__all__ += ["VictoryPointTransaction", "_attributed_destruction_state"]
__all__ += ["_build_tracking_destruction", "_record_tracking_destruction_models"]
__all__ += ["_runtime_policy", "_runtime_rule", "_source_primary_mission", "_source_rule"]
__all__ += ["_test_primary_state_evidence", "_turn_start_component", "_turn_start_snapshot"]
__all__ += ["_unattributed_destruction_state", "_validate_destruction_states"]
__all__ += ["_validate_turn_start_snapshots", "build_primary_rules_unit_turn_start_snapshot"]
__all__ += ["build_primary_unit_destruction_state"]
__all__ += ["current_primary_component_turn_start_membership"]
__all__ += ["current_primary_rules_unit_turn_start_membership", "objective_control_record_hash"]
__all__ += ["primary_rules_unit_turn_start_membership_for_lineage"]
__all__ += ["primary_rules_unit_turn_start_snapshots_from_payload"]
__all__ += ["primary_rules_unit_turn_start_snapshots_with_created_unit"]
__all__ += ["primary_unit_destruction_id", "record_primary_destroyed_model_departures"]
__all__ += ["record_primary_rules_unit_turn_start_snapshot"]
__all__ += ["record_primary_unit_destructions_for_destroyed_models"]
__all__ += ["record_primary_unit_destructions_for_end_turn_cleanup"]
__all__ += ["validate_primary_objective_turn_start_states"]
__all__ += ["validate_primary_rules_unit_turn_start_snapshots"]
__all__ += ["validate_primary_unit_destruction_source_witness_identity"]
__all__ += ["validate_primary_unit_destruction_states"]
__all__ += ["validate_primary_unit_destruction_turn_start_evidence"]
__all__ += ["validate_victory_point_ledger_policy"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
