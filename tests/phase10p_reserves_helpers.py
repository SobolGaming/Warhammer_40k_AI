from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseHandler,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    LargeModelReservePlacementException,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def battle_state_with_reserve(
    *,
    reserve_base_diameter_mm: float = 200.0,
    reserve_model_count: int = 1,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> tuple[GameState, BattlefieldScenario, ReserveState, UnitInstance]:
    config = reserve_config(ruleset_descriptor=ruleset_descriptor or ruleset())
    armies = mustered_armies(config)
    armies = with_reserve_unit_geometry(
        armies=armies,
        base_diameter_mm=reserve_base_diameter_mm,
        reserve_model_count=reserve_model_count,
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield_state)
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            (ruleset_descriptor or ruleset()).mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, scenario, reserve_state, reserve_unit


def submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def submit_reserve_placement_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    reserve_unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: UnitPlacement,
    result_id: str,
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = (),
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=reserve_unit.unit_instance_id,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
        large_model_exceptions=large_model_exceptions,
    ).to_payload()
    return submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, object]:
    for record in reversed(decisions.event_log.records):
        if record.event_type == event_type:
            payload = record.payload
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)
    raise AssertionError(f"event {event_type} not found")


def with_reserve_unit_geometry(
    *,
    armies: tuple[ArmyDefinition, ...],
    base_diameter_mm: float,
    reserve_model_count: int,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        base_size = BaseSizeDefinition.circular(base_diameter_mm)
        updated_models = tuple(
            replace(
                model,
                base_size=base_size if index == 0 else model.base_size,
                geometry=(
                    ModelGeometry.from_base_size(
                        base_size,
                        geometry_source_id="phase10p-oversized-base",
                        keywords=reserve_unit.keywords,
                    )
                    if index == 0
                    else model.geometry
                ),
            )
            for index, model in enumerate(reserve_unit.own_models[:reserve_model_count])
        )
        updated_unit = replace(reserve_unit, own_models=updated_models)
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return tuple(updated_armies)


def single_model_reserve_placement(*, reserve_unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return reserve_placement(reserve_unit=reserve_unit, poses=(pose,))


def reserve_placement(*, reserve_unit: UnitInstance, poses: tuple[Pose, ...]) -> UnitPlacement:
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def south_edge_touching_pose(*, base_diameter_mm: float, x: float) -> Pose:
    return Pose.at(
        x=x,
        y=base_radius_inches(base_diameter_mm),
        z=0.0,
        facing_degrees=0.0,
    )


def base_radius_inches(base_diameter_mm: float) -> float:
    return (base_diameter_mm / 25.4) / 2.0


def with_model_pose(
    scenario: BattlefieldScenario,
    *,
    model_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    model_placement = scenario.battlefield_state.model_placement_by_id(model_instance_id)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        model_placement.unit_instance_id
    )
    updated_model_placements = tuple(
        replace(placement, pose=pose)
        if placement.model_instance_id == model_instance_id
        else placement
        for placement in unit_placement.model_placements
    )
    updated_unit_placement = replace(
        unit_placement,
        model_placements=updated_model_placements,
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_unit_placement),
    )


def ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase10p-test")


def reserve_config(*, ruleset_descriptor: RulesetDescriptor) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10p-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    unit_selection(unit_selection_id="intercessor-unit-1"),
                    unit_selection(unit_selection_id="intercessor-unit-2"),
                ),
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(unit_selection(unit_selection_id="intercessor-unit-3"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=unit_selections,
    )


def unit_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
