from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_conditions_bindings import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    TABLE_QUARTER_IDS,
    Any,
    BattlefieldRegionKind,
    BattlePhase,
    GameState,
    JsonValue,
    MissionScoringPolicy,
    MissionSetup,
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    Pose,
    PrimaryObjectiveTurnStartState,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryScoringConditionContext,
    PrimaryScoringSpatialEvidence,
    PrimaryScoringStateEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionEvidence,
    PrimaryUnitDestructionState,
    UnitPlacement,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointTransaction,
    battle_state,
    build_primary_scoring_state_evidence,
    cast,
    default_unit_selection,
    evaluate_primary_scoring_condition,
    home_objective_ids,
    mission_scoring_policies_from_setup,
    objective_control_record_hash,
    opponent_home_control_evidence,
    primary_score_count_evidence,
    replace,
    resolve_objective_control,
    validate_primary_victory_point_award,
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
    context = PrimaryScoringConditionContext(**parameters)
    if corruption == "inactive_player":
        evaluate_primary_scoring_condition(
            condition="control_one_or_more_central_objectives",
            context=context,
        )


def _primary_vp_policy_fixture(
    mission_setup: MissionSetup,
) -> tuple[
    GameState,
    MissionScoringPolicy,
    ObjectiveControlRecord,
    PrimaryScoringStateEvidence,
    VictoryPointAward,
]:
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
    policies = mission_scoring_policies_from_setup(mission_setup)
    policy = policies.policy_for_player("player-a")
    state, boundary, state_evidence = _primary_scoring_state_evidence(
        mission_setup=mission_setup,
        record=boundary,
    )
    award = next(
        candidate
        for candidate in policies.primary_awards_from_objective_control(
            record=boundary,
            authoritative_state=state,
        )
        if cast(dict[str, object], candidate.metadata)["scoring_rule_id"]
        == "battlefield-dominance-each-objective"
    )
    binding = validate_primary_victory_point_award(
        policy=policy,
        award=award,
        objective_control_records=(boundary,),
        primary_scoring_state_evidence_records=(state_evidence,),
        turn_order=("player-a", "player-b"),
        expected_boundary_active_player_id="player-a",
    )
    assert binding.scoring_rule_id == "battlefield-dominance-each-objective"
    return state, policy, boundary, state_evidence, award


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


def _primary_scoring_state_evidence(
    *,
    mission_setup: MissionSetup,
    record: ObjectiveControlRecord,
) -> tuple[GameState, ObjectiveControlRecord, PrimaryScoringStateEvidence]:
    expected_results_by_objective_id = {
        result.objective_id: (result.status, result.controlled_by_player_id)
        for result in record.results
    }
    mission_markers_by_id = {
        marker.objective_marker_id: marker for marker in mission_setup.objective_markers
    }
    if set(expected_results_by_objective_id) != set(mission_markers_by_id):
        raise AssertionError(
            "Primary scoring evidence fixture requires one result per mission objective."
        )
    controlled_objective_ids_by_player: dict[str, list[str]] = {
        "player-a": [],
        "player-b": [],
    }
    for result in record.results:
        if result.status is ObjectiveControlStatus.UNCONTROLLED:
            continue
        if (
            result.status is not ObjectiveControlStatus.CONTROLLED
            or result.controlled_by_player_id not in controlled_objective_ids_by_player
        ):
            raise AssertionError(
                "Primary scoring evidence fixture supports controlled or uncontrolled "
                "mission objectives for the fixture players."
            )
        controlled_objective_ids_by_player[result.controlled_by_player_id].append(
            result.objective_id
        )
    if len(controlled_objective_ids_by_player["player-b"]) > 1:
        raise AssertionError(
            "Primary scoring evidence fixture provisions one player-b scoring unit."
        )
    state = battle_state(
        player_a_units=tuple(
            default_unit_selection(f"phase17n-primary-control-unit-{index + 1}")
            for index in range(max(1, len(controlled_objective_ids_by_player["player-a"])))
        )
    )
    if state.battlefield_state is None:
        raise AssertionError("Primary scoring evidence fixture requires battlefield state.")
    state.game_id = record.game_id
    state.mission_setup = mission_setup
    state.primary_objective_turn_start_states = []
    state.primary_terrain_trap_states = []
    state.primary_unit_destruction_states = []
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_id=record.battlefield_id,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    armies_by_player_id = {army.player_id: army for army in state.army_definitions}
    battlefield_state = state.battlefield_state
    for player_id in ("player-a", "player-b"):
        controlled_objective_ids = controlled_objective_ids_by_player[player_id]
        units = armies_by_player_id[player_id].units
        if len(controlled_objective_ids) > len(units):
            raise AssertionError(
                f"Primary scoring evidence fixture lacks {player_id} scoring units."
            )
        for index, unit in enumerate(units):
            placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
            if index < len(controlled_objective_ids):
                marker = mission_markers_by_id[controlled_objective_ids[index]]
                anchor = (marker.x_inches, marker.y_inches, marker.z_inches)
            elif player_id == "player-a":
                anchor = (4.0, 4.0, 0.0)
            else:
                anchor = (
                    mission_setup.battlefield_width_inches - 4.0,
                    mission_setup.battlefield_depth_inches - 4.0,
                    0.0,
                )
            battlefield_state = battlefield_state.with_unit_placement(
                _primary_scoring_unit_placement_at_anchor(
                    placement,
                    anchor=anchor,
                )
            )
    state.battlefield_state = battlefield_state
    state.battle_round = record.battle_round
    state.active_player_id = record.active_player_id
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase(record.phase))
    authoritative_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=record.timing,
            phase=BattlePhase(record.phase),
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    authoritative_results_by_objective_id = {
        result.objective_id: (result.status, result.controlled_by_player_id)
        for result in authoritative_record.results
    }
    if authoritative_results_by_objective_id != expected_results_by_objective_id:
        raise AssertionError(
            "Primary scoring evidence physical fixture did not resolve the requested "
            "objective controllers."
        )
    state.record_objective_control_record(authoritative_record)
    evidence = build_primary_scoring_state_evidence(
        scoring_player_id=authoritative_record.active_player_id,
        state=state,
        record=authoritative_record,
        end_of_battle=False,
    )
    return state, authoritative_record, evidence


def _primary_scoring_unit_placement_at_anchor(
    placement: UnitPlacement,
    *,
    anchor: tuple[float, float, float],
) -> UnitPlacement:
    model_offsets = (
        (-1.4, -1.4),
        (1.4, -1.4),
        (0.0, 0.0),
        (-1.4, 1.4),
        (1.4, 1.4),
    )
    if len(placement.model_placements) != len(model_offsets):
        raise AssertionError("Primary scoring evidence fixture requires five-model scoring units.")
    anchor_x, anchor_y, anchor_z = anchor
    return placement.with_model_placements(
        tuple(
            model_placement.with_pose(
                Pose.at(
                    anchor_x + offset_x,
                    anchor_y + offset_y,
                    anchor_z,
                    facing_degrees=model_placement.pose.facing.degrees,
                )
            )
            for model_placement, (offset_x, offset_y) in zip(
                placement.model_placements,
                model_offsets,
                strict=True,
            )
        )
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


__all__: list[str] = []
__all__ += ["Any", "BattlePhase", "BattlefieldRegionKind", "GameState", "JsonValue"]
__all__ += ["MissionScoringPolicy", "MissionSetup", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlContribution", "ObjectiveControlRecord", "ObjectiveControlResult"]
__all__ += ["ObjectiveControlScore", "ObjectiveControlStatus", "ObjectiveControlTiming"]
__all__ += ["PRIMARY_SCORING_SPATIAL_CONDITIONS", "Pose", "PrimaryObjectiveTurnStartState"]
__all__ += ["PrimaryRulesUnitTurnStartSnapshot", "PrimaryScoringConditionContext"]
__all__ += ["PrimaryScoringSpatialEvidence", "PrimaryScoringStateEvidence"]
__all__ += ["PrimaryTableQuarterUnitWitness", "PrimaryUnattributedDestructionCause"]
__all__ += ["TABLE_QUARTER_IDS", "PrimaryUnitDestructionEvidence", "PrimaryUnitDestructionState"]
__all__ += ["UnitPlacement", "VictoryPointAward", "VictoryPointLedger", "VictoryPointTransaction"]
__all__ += ["_control_record", "_controlled_result", "_primary_historical_evidence_fixture"]
__all__ += ["_primary_scoring_state_evidence", "_primary_scoring_unit_placement_at_anchor"]
__all__ += ["_primary_transaction_from_award", "_primary_vp_policy_fixture"]
__all__ += ["_run_invalid_primary_scoring_operation", "_run_primary_scoring_context_corruption"]
__all__ += ["_spatial_evidence", "_territory_objective_ids", "battle_state"]
__all__ += ["build_primary_scoring_state_evidence", "cast", "default_unit_selection"]
__all__ += ["evaluate_primary_scoring_condition", "home_objective_ids"]
__all__ += ["mission_scoring_policies_from_setup", "objective_control_record_hash"]
__all__ += ["opponent_home_control_evidence", "primary_score_count_evidence", "replace"]
__all__ += ["resolve_objective_control", "validate_primary_victory_point_award"]
