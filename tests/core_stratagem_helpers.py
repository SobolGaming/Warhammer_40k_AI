from __future__ import annotations

from dataclasses import replace

from tests.setup_completion_helpers import (
    enter_battle_for_fixture,
)
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import (
    GameLifecycle,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_turn_start_evidence_events,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def _replace_unit_keywords(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            with_unit_keywords(unit, keywords=keywords)
            if unit.unit_instance_id == unit_instance_id
            else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"Missing unit {unit_instance_id}.")


def _replace_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    assert len(placement.model_placements) == len(poses)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(pose)
                    for model_placement, pose in zip(placement.model_placements, poses, strict=True)
                )
            )
        )
    )


def _clear_terrain(state: GameState) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.battlefield_state = replace(battlefield_state, terrain_features=())


def _move_unit_to_reserves(
    lifecycle: GameLifecycle,
    *,
    player_id: str,
    unit_instance_id: str,
    reserve_kind: ReserveKind = ReserveKind.RESERVES,
) -> tuple[ReserveState, UnitInstance, ArmyDefinition]:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(battlefield_state.without_unit_placement(unit_instance_id))
    reserve_state = ReserveState.declared_before_battle(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_kind=reserve_kind,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=state.mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    state.record_reserve_state(reserve_state)
    lifecycle.decision_controller.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "unit_instance_id": unit_instance_id,
            "reserve_state": reserve_state.to_payload(),
        },
    )
    army = state.army_definition_for_player(player_id)
    assert army is not None
    return reserve_state, army.unit_by_id(unit_instance_id), army


def _reserve_placement(
    *,
    army: ArmyDefinition,
    reserve_unit: UnitInstance,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring-it-down"),
    )


def _unadvanced_battle_lifecycle(
    config: GameConfig | None = None,
    *,
    keyword_replacements: tuple[tuple[str, tuple[str, ...]], ...] = (),
    pose_replacements: tuple[tuple[str, tuple[Pose, ...]], ...] = (),
    clear_terrain: bool = False,
) -> GameLifecycle:
    config = _config() if config is None else config
    decisions = DecisionController()
    state = _battle_state(
        config=config,
        decisions=decisions,
        keyword_replacements=keyword_replacements,
        pose_replacements=pose_replacements,
        clear_terrain=clear_terrain,
    )
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )


def _battle_lifecycle(
    config: GameConfig | None = None,
    *,
    battle_round: int = 1,
    active_player_id: str = "player-a",
    reserve_unit: tuple[str, str] | None = None,
    reserve_units: tuple[tuple[str, str], ...] = (),
    reserve_kind: ReserveKind = ReserveKind.RESERVES,
    keyword_replacements: tuple[tuple[str, tuple[str, ...]], ...] = (),
    pose_replacements: tuple[tuple[str, tuple[Pose, ...]], ...] = (),
    feel_no_pain_source_replacements: tuple[
        tuple[str, tuple[FeelNoPainSource, ...], bool], ...
    ] = (),
    clear_terrain: bool = False,
) -> GameLifecycle:
    if battle_round < 1:
        raise AssertionError("Battle lifecycle fixture round must be positive.")
    lifecycle = _unadvanced_battle_lifecycle(
        config,
        pose_replacements=pose_replacements,
        clear_terrain=clear_terrain,
    )
    state = _state(lifecycle)
    for unit_instance_id, keywords in keyword_replacements:
        _replace_unit_keywords(
            state,
            unit_instance_id=unit_instance_id,
            keywords=keywords,
        )
    for model_instance_id, sources, decline_allowed in feel_no_pain_source_replacements:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model_instance_id,
            sources=sources,
            decline_allowed=decline_allowed,
        )
    _record_default_fixed_secondary_choices_for_missing_players(state)
    for reserve_player_id, reserve_unit_instance_id in (
        (*reserve_units, reserve_unit) if reserve_unit is not None else reserve_units
    ):
        _move_unit_to_reserves(
            lifecycle,
            player_id=reserve_player_id,
            unit_instance_id=reserve_unit_instance_id,
            reserve_kind=reserve_kind,
        )
    lifecycle = _complete_current_command_for_fixture(lifecycle)
    if battle_round == 1 and active_player_id != _state(lifecycle).turn_order[0]:
        state = _state(lifecycle)
        if active_player_id not in state.player_ids:
            raise AssertionError("Battle lifecycle fixture active player is unknown.")
        while not (
            state.active_player_id == active_player_id
            and state.current_battle_phase is BattlePhase.COMMAND
        ):
            _advance_battle_phase_for_fixture(lifecycle)
        lifecycle = _complete_current_command_for_fixture(lifecycle)
    if battle_round > 1:
        status = lifecycle.advance_until_decision_or_terminal()
        while True:
            state = _state(lifecycle)
            if (
                state.battle_round == battle_round
                and state.active_player_id == state.turn_order[0]
                and state.current_battle_phase is BattlePhase.MOVEMENT
            ):
                break
            request = _decision_request(status)
            if request.decision_type == "select_movement_unit":
                selected_option_id = request.options[0].option_id
            elif request.decision_type == "select_movement_action":
                selected_option_id = "remain_stationary"
            elif request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
                status = lifecycle.submit_decision(
                    DecisionResult(
                        result_id=(
                            f"phase12c-round-advance:{state.battle_round}:"
                            f"{state.active_player_id}:decline-stratagem"
                        ),
                        request_id=request.request_id,
                        decision_type=request.decision_type,
                        actor_id=request.actor_id,
                        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                        payload=stratagem_decline_payload(),
                    )
                )
                continue
            else:
                raise AssertionError(
                    "Round-advance fixture encountered an unexpected decision type: "
                    f"{request.decision_type}."
                )
            status = lifecycle.submit_decision(
                DecisionResult.for_request(
                    result_id=(
                        f"phase12c-round-advance:{state.battle_round}:"
                        f"{state.active_player_id}:{request.decision_type}"
                    ),
                    request=request,
                    selected_option_id=selected_option_id,
                )
            )
    state = _state(lifecycle)
    assert state.battle_round == battle_round
    assert state.active_player_id == active_player_id
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    return lifecycle


def _complete_current_command_for_fixture(lifecycle: GameLifecycle) -> GameLifecycle:
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.COMMAND
    completed = BattleRoundFlow(
        phase_handlers={BattlePhase.COMMAND: CommandPhaseHandler()},
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        army_catalog=lifecycle.config.army_catalog,
    ).advance(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_queue=lifecycle.reaction_queue,
    )
    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert _state(lifecycle).current_battle_phase is BattlePhase.MOVEMENT
    return lifecycle


def _advance_battle_phase_for_fixture(lifecycle: GameLifecycle) -> None:
    from warhammer40k_core.engine.battle_round_flow import (
        _emit_objective_control_boundary_event_if_missing,  # pyright: ignore[reportPrivateUsage]
    )

    state = _state(lifecycle)
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record = state.determine_current_phase_end_objective_control()
    _emit_objective_control_boundary_event_if_missing(
        decisions=lifecycle.decision_controller, record=record
    )
    if state.current_battle_phase is BattlePhase.FIGHT:
        record = state.prepare_current_turn_end_boundary(
            completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
        )
        _emit_objective_control_boundary_event_if_missing(
            decisions=lifecycle.decision_controller, record=record
        )
    state.advance_to_next_battle_phase(event_log=lifecycle.decision_controller.event_log)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )


def _battle_state(
    config: GameConfig | None = None,
    *,
    decisions: DecisionController | None = None,
    keyword_replacements: tuple[tuple[str, tuple[str, ...]], ...] = (),
    pose_replacements: tuple[tuple[str, tuple[Pose, ...]], ...] = (),
    clear_terrain: bool = False,
) -> GameState:
    resolved_config = _config() if config is None else config
    armies = _mustered_armies(resolved_config)
    state = GameState.from_config(resolved_config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase12c-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    for unit_instance_id, keywords in keyword_replacements:
        _replace_unit_keywords(
            state,
            unit_instance_id=unit_instance_id,
            keywords=keywords,
        )
    for unit_instance_id, poses in pose_replacements:
        _replace_unit_poses(
            state,
            unit_instance_id=unit_instance_id,
            poses=poses,
        )
    if clear_terrain:
        _clear_terrain(state)
    enter_battle_for_fixture(state, decisions=decisions)
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _config(
    *,
    beta_unit_selection_ids: tuple[str, ...] = ("enemy-unit",),
    beta_datasheet_ids: tuple[str, ...] | None = None,
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id="phase12c-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase12c-test"
        ),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=beta_unit_selection_ids,
                datasheet_ids=beta_datasheet_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str | None = None,
    unit_selection_ids: tuple[str, ...] | None = None,
    datasheet_ids: tuple[str, ...] | None = None,
) -> ArmyMusterRequest:
    if unit_selection_id is not None and unit_selection_ids is not None:
        raise AssertionError("Use unit_selection_id or unit_selection_ids, not both.")
    resolved_unit_selection_ids: tuple[str, ...]
    if unit_selection_ids is None:
        if unit_selection_id is None:
            raise AssertionError("Expected at least one unit selection id.")
        resolved_unit_selection_ids = (unit_selection_id,)
    else:
        resolved_unit_selection_ids = unit_selection_ids
    resolved_datasheet_ids = (
        tuple("core-intercessor-like-infantry" for _ in resolved_unit_selection_ids)
        if datasheet_ids is None
        else datasheet_ids
    )
    if len(resolved_datasheet_ids) != len(resolved_unit_selection_ids):
        raise AssertionError("Datasheet IDs must align with unit selection IDs.")
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=(
            *(
                UnitMusterSelection(
                    unit_selection_id=resolved_unit_selection_id,
                    datasheet_id=datasheet_id,
                    model_profile_selections=(
                        ModelProfileSelection(
                            model_profile_id="core-intercessor-like",
                            model_count=5,
                        ),
                    ),
                )
                for resolved_unit_selection_id, datasheet_id in zip(
                    resolved_unit_selection_ids,
                    resolved_datasheet_ids,
                    strict=True,
                )
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _record_default_fixed_secondary_choices_for_missing_players(state: GameState) -> None:
    for player_id in state.missing_secondary_mission_player_ids():
        state.record_secondary_mission_choice(
            _secondary_choice(player_id=player_id, mode=SecondaryMissionMode.FIXED)
        )


__all__ = [
    "_battle_lifecycle",
    "_battle_state",
    "_clear_terrain",
    "_config",
    "_decision_request",
    "_move_unit_to_reserves",
    "_record_default_fixed_secondary_choices_for_missing_players",
    "_replace_unit_keywords",
    "_replace_unit_poses",
    "_reserve_placement",
    "_secondary_choice",
    "_state",
    "_unadvanced_battle_lifecycle",
]
