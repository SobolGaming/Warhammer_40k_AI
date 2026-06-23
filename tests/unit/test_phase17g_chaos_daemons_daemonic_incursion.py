from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from tests.unit.test_phase10p_reserves import (
    _base_radius_inches,  # pyright: ignore[reportPrivateUsage]
    _battle_state_with_reserve,  # pyright: ignore[reportPrivateUsage]
    _decision_request,  # pyright: ignore[reportPrivateUsage]
    _last_event_payload,  # pyright: ignore[reportPrivateUsage]
    _single_model_reserve_placement,  # pyright: ignore[reportPrivateUsage]
    _south_edge_touching_pose,  # pyright: ignore[reportPrivateUsage]
    _submit_handler_decision,  # pyright: ignore[reportPrivateUsage]
    _submit_reserve_placement_payload,  # pyright: ignore[reportPrivateUsage]
    _with_model_pose,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
    rule,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseHandler,
    MovementPhaseState,
)
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceHookRegistry,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReservePlacementViolationCode,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

_DAEMONIC_INCURSION_DATASHEET_ID = "phase17g-daemonic-incursion-daemon"
_OTHER_DAEMON_DETACHMENT_ID = "warptide"
_RESERVE_UNIT_ID = "army-alpha:intercessor-unit-1"
_ANCHOR_UNIT_ID = "army-alpha:intercessor-unit-2"
_RESERVE_BASE_DIAMETER_MM = 32.0


def test_daemonic_incursion_runtime_hook_materializes_only_for_selected_detachment() -> None:
    direct_contribution = rule.runtime_contribution()
    summary = build_runtime_content_bundle(_daemonic_incursion_config()).to_summary_payload()

    assert direct_contribution.contribution_id == rule.CONTRIBUTION_ID
    assert not direct_contribution.contribution_id.endswith(":scaffold")
    assert rule.WARP_RIFTS_HOOK_ID in summary["reserve_arrival_distance_hook_ids"]
    assert rule.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.daemonic_incursion.manifest")
        for path in summary["selected_module_paths"]
    )

    other_summary = build_runtime_content_bundle(
        _daemonic_incursion_config(
            daemon_detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
            game_id="phase17g-daemonic-incursion-not-selected",
        )
    ).to_summary_payload()

    assert rule.WARP_RIFTS_HOOK_ID not in other_summary["reserve_arrival_distance_hook_ids"]


def test_warp_rifts_shadow_allows_deep_strike_more_than_six_from_enemy() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-shadow-arrival",
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    arrival_event = _last_event_payload(status.decisions, "reinforcement_unit_arrived")
    assert arrival_event["placement_kind"] == BattlefieldPlacementKind.DEEP_STRIKE.value


def test_warp_rifts_matching_greater_daemon_anchor_allows_deep_strike_outside_shadow() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=target_pose,
        distance_inches=4.0,
    )

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-anchor-arrival",
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED


def test_warp_rifts_requires_shared_god_keyword_for_greater_daemon_anchor() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state(
        reserve_god_keyword="Tzeentch",
        anchor_god_keyword="Khorne",
    )
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=target_pose,
        distance_inches=4.0,
    )

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-nonmatching-anchor",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    violations = cast(list[dict[str, JsonValue]], status.payload["violations"])
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE.value in {
        cast(str, violation["violation_code"]) for violation in violations
    }
    remaining_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert remaining_state is not None
    assert remaining_state.status is ReserveStatus.IN_RESERVES


def test_warp_rifts_does_not_reduce_strategic_reserves_enemy_distance() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state(
        reserve_kind=ReserveKind.STRATEGIC_RESERVES
    )
    target_pose = _south_edge_touching_pose(base_diameter_mm=_RESERVE_BASE_DIAMETER_MM, x=16.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)

    status = _submit_reserve_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        battle_round=3,
        result_id="phase17g-warp-rifts-strategic-reserves",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    violations = cast(list[dict[str, JsonValue]], status.payload["violations"])
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE.value in {
        cast(str, violation["violation_code"]) for violation in violations
    }
    remaining_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert remaining_state is not None
    assert remaining_state.status is ReserveStatus.IN_RESERVES


def _daemonic_incursion_reserve_state(
    *,
    reserve_god_keyword: str = "Khorne",
    anchor_god_keyword: str = "Khorne",
    reserve_kind: ReserveKind = ReserveKind.DEEP_STRIKE,
) -> tuple[GameState, ReserveState, UnitInstance]:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=_RESERVE_BASE_DIAMETER_MM
    )
    state.army_definitions = list(
        _with_daemonic_incursion_units(
            tuple(state.army_definitions),
            reserve_god_keyword=reserve_god_keyword,
            anchor_god_keyword=anchor_god_keyword,
        )
    )
    updated_reserve_state = replace(reserve_state, reserve_kind=reserve_kind)
    state.replace_reserve_state(updated_reserve_state)
    reserve_unit = _unit_by_id(state, _RESERVE_UNIT_ID)
    return state, updated_reserve_state, reserve_unit


def _submit_deep_strike_arrival(
    *,
    state: GameState,
    reserve_state: ReserveState,
    reserve_unit: UnitInstance,
    target_pose: Pose,
    result_id: str,
) -> _ResolvedArrivalStatus:
    return _submit_reserve_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        battle_round=1,
        result_id=result_id,
    )


def _submit_reserve_arrival(
    *,
    state: GameState,
    reserve_state: ReserveState,
    reserve_unit: UnitInstance,
    target_pose: Pose,
    placement_kind: BattlefieldPlacementKind,
    battle_round: int,
    result_id: str,
) -> _ResolvedArrivalStatus:
    _set_movement_ready_for_reinforcements(state, battle_round=battle_round)
    handler = MovementPhaseHandler(
        ruleset_descriptor=_ruleset(),
        reserve_arrival_distance_hooks=ReserveArrivalDistanceHookRegistry.from_bindings(
            rule.runtime_contribution().reserve_arrival_distance_hook_bindings
        ),
    )
    decisions = DecisionController()
    selection_status = handler.begin_phase(state=state, decisions=decisions)
    selection_request = _decision_request(selection_status)
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id=f"{result_id}:select",
    )
    placement_request = _decision_request(placement_status)
    result_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=placement_kind,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=target_pose,
        ),
        result_id=result_id,
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)
    assert result_status is not None
    assert isinstance(result_status.payload, dict)
    return _ResolvedArrivalStatus(
        status_kind=result_status.status_kind,
        payload=result_status.payload,
        decisions=decisions,
    )


@dataclass(frozen=True, slots=True)
class _ResolvedArrivalStatus:
    status_kind: LifecycleStatusKind
    payload: dict[str, JsonValue]
    decisions: DecisionController


def _set_movement_ready_for_reinforcements(state: GameState, *, battle_round: int) -> None:
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = battle_round
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=(_ANCHOR_UNIT_ID,),
        moved_unit_ids=(_ANCHOR_UNIT_ID,),
    )


def _with_daemonic_incursion_units(
    armies: tuple[ArmyDefinition, ...],
    *,
    reserve_god_keyword: str,
    anchor_god_keyword: str,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id == "army-alpha":
            reserve_unit = _as_daemon_unit(
                army.unit_by_id(_RESERVE_UNIT_ID),
                name="Bloodletters",
                keywords=("Infantry", reserve_god_keyword, "DEEP_STRIKE"),
            )
            anchor_unit = _as_daemon_unit(
                army.unit_by_id(_ANCHOR_UNIT_ID),
                name="Bloodthirster",
                keywords=("Monster", anchor_god_keyword),
            )
            updated_armies.append(
                replace(
                    army,
                    detachment_selection=DetachmentSelection(
                        faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                        detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
                    ),
                    units=tuple(
                        reserve_unit
                        if unit.unit_instance_id == reserve_unit.unit_instance_id
                        else anchor_unit
                        if unit.unit_instance_id == anchor_unit.unit_instance_id
                        else unit
                        for unit in army.units
                    ),
                )
            )
            continue
        updated_armies.append(army)
    return tuple(updated_armies)


def _as_daemon_unit(
    unit: UnitInstance,
    *,
    name: str,
    keywords: tuple[str, ...],
) -> UnitInstance:
    return replace(
        unit,
        name=name,
        keywords=keywords,
        faction_keywords=(rule.LEGIONES_DAEMONICA,),
        own_models=tuple(
            _with_base_size(model, base_diameter_mm=_RESERVE_BASE_DIAMETER_MM)
            for model in unit.own_models
        ),
    )


def _place_enemy_at_base_distance(
    *,
    state: GameState,
    target_pose: Pose,
    distance_inches: float,
) -> None:
    enemy_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    enemy_model_id = enemy_unit.own_models[0].model_instance_id
    radius = _base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
    _place_model(
        state=state,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=target_pose.position.x + (radius * 2.0) + distance_inches,
            y=target_pose.position.y,
            z=0.0,
            facing_degrees=0.0,
        ),
    )


def _place_anchor_at_base_distance(
    *,
    state: GameState,
    target_pose: Pose,
    distance_inches: float,
) -> None:
    anchor_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    anchor_model_id = anchor_unit.own_models[0].model_instance_id
    radius = _base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
    _place_model(
        state=state,
        model_instance_id=anchor_model_id,
        pose=Pose.at(
            x=target_pose.position.x,
            y=target_pose.position.y - (radius * 2.0) - distance_inches,
            z=0.0,
            facing_degrees=0.0,
        ),
    )


def _place_model(
    *,
    state: GameState,
    model_instance_id: str,
    pose: Pose,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    updated_scenario = _with_model_pose(
        scenario,
        model_instance_id=model_instance_id,
        pose=pose,
    )
    state.replace_battlefield_state(updated_scenario.battlefield_state)


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"unit not found: {unit_instance_id}")


def _with_base_size(model: ModelInstance, *, base_diameter_mm: float) -> ModelInstance:
    if type(model) is not ModelInstance:
        raise AssertionError("test base-size helper requires ModelInstance")
    base_size = BaseSizeDefinition.circular(base_diameter_mm)
    return replace(
        model,
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            geometry_source_id="phase17g-daemonic-incursion-base",
            keywords=(),
        ),
    )


def _daemonic_incursion_config(
    *,
    game_id: str = "phase17g-daemonic-incursion-game",
    daemon_detachment_id: str = rule.DAEMONIC_INCURSION_DETACHMENT_ID,
) -> GameConfig:
    catalog = _daemonic_incursion_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=daemon_detachment_id,
                unit_selection_id="daemon-unit",
                datasheet_id=_DAEMONIC_INCURSION_DATASHEET_ID,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id="enemy-unit",
                datasheet_id="core-intercessor-like-infantry",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _daemonic_incursion_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = replace(
        base_datasheet,
        datasheet_id=_DAEMONIC_INCURSION_DATASHEET_ID,
        name="Daemonic Incursion Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Khorne", "Deep Strike"),
            faction_keywords=(rule.LEGIONES_DAEMONICA,),
        ),
        source_ids=("phase17g:test:chaos-daemons:daemonic-incursion-daemon",),
    )
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=(rule.LEGIONES_DAEMONICA,),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.DAEMONIC_INCURSION_DETACHMENT_ID,
                name="Daemonic Incursion",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_DAEMONIC_INCURSION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:"
                    "chaos-daemons:daemonic-incursion",
                ),
            ),
            DetachmentDefinition(
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                name="Warptide",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_DAEMONIC_INCURSION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase17g-daemonic-incursion-test"
    )
