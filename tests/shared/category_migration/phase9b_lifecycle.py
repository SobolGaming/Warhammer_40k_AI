from __future__ import annotations

import inspect
import json
from dataclasses import replace
from typing import cast

import pytest

from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.model_geometry_helpers import accepted_model_geometry
from tests.phase17n_secondary_mission_helpers import drain_pending_secondary_mission_setup
from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    RulesetDescriptor,
    SetupSequenceDescriptor,
    SetupStepKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.game_state_payloads import GameConfigPayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
    SetupStep,
    game_lifecycle_stage_from_token,
    lifecycle_status_kind_from_token,
)
from warhammer40k_core.engine.phases.charge import ChargePhaseState, ChargingUnitSelection
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.geometry.model_geometry import GeometrySourceKind, HeightSourceKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def _config(
    *,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    army_muster_requests: tuple[ArmyMusterRequest, ...] | None = None,
    max_lifecycle_transitions: int = DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] | None = None,
) -> GameConfig:
    descriptor = ruleset_descriptor
    if descriptor is None:
        descriptor = RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase9b-test"
        )
    catalog = ArmyCatalog.phase9a_canonical_content_pack() if army_catalog is None else army_catalog
    return GameConfig(
        game_id="phase9b-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_requests(catalog) if army_muster_requests is None else army_muster_requests
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        max_lifecycle_transitions=max_lifecycle_transitions,
        mission_setup=_mission_setup(),
        model_geometries=model_geometries,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _army_muster_requests(catalog: ArmyCatalog) -> tuple[ArmyMusterRequest, ...]:
    return (
        _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selection_id="intercessor-unit-1",
        ),
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selection_id="intercessor-unit-2",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
                wargear_selections=wargear_selections,
            ),
        ),
    )


def _descriptor_with_sequences(
    *,
    setup_steps: tuple[SetupStepKind, ...] | None = None,
    battle_phases: tuple[BattlePhaseKind, ...] | None = None,
) -> RulesetDescriptor:
    base = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase9b-sequence-test"
    )
    return RulesetDescriptor(
        ruleset_id=base.ruleset_id,
        source_date=base.source_date,
        descriptor_version=base.descriptor_version,
        engagement_policy=base.engagement_policy,
        movement_policy=base.movement_policy,
        charge_policy=base.charge_policy,
        fight_policy=base.fight_policy,
        terrain_movement_policy=base.terrain_movement_policy,
        terrain_visibility_policy=base.terrain_visibility_policy,
        objective_policy=base.objective_policy,
        coherency_policy=base.coherency_policy,
        fly_policy=base.fly_policy,
        mission_policy=base.mission_policy,
        setup_sequence=SetupSequenceDescriptor(
            steps=setup_steps
            if setup_steps is not None
            else SetupSequenceDescriptor.warhammer_40000_eleventh_default().steps
        ),
        battle_phase_sequence=BattlePhaseSequenceDescriptor(
            phases=battle_phases
            if battle_phases is not None
            else BattlePhaseSequenceDescriptor.warhammer_40000_eleventh_default().phases
        ),
    )


def _start_lifecycle(config: GameConfig | None = None) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    return lifecycle


def _state(lifecycle: GameLifecycle) -> GameStatePayload:
    payload = lifecycle.to_payload()
    return payload["state"]


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest:
    return lifecycle.decision_controller.queue.peek_next()


def _request_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    assert isinstance(request.payload, dict)
    return request.payload


def _public_secondary_choices(payload: dict[str, JsonValue]) -> list[JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    return choices


def _state_battle_phase(state: GameState) -> BattlePhaseKind | None:
    return state.current_battle_phase


def _submit_pending(
    lifecycle: GameLifecycle,
    *,
    option_id: str,
    result_number: int,
) -> LifecycleStatus:
    request = _pending_request(lifecycle)
    result = DecisionResult.for_request(
        result_id=f"decision-result-{result_number:06d}",
        request=request,
        selected_option_id=option_id,
    )
    return lifecycle.submit_decision(result)


def _decline_stratagem_window_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_number: int,
) -> LifecycleStatus:
    current = drain_pending_secondary_mission_setup(
        lifecycle,
        status,
        result_id_prefix=f"decision-result-{result_number:06d}-secondary-setup",
    )
    request = current.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return current
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"decision-result-{result_number:06d}",
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _advance_to_secondary_mission_step(lifecycle: GameLifecycle) -> None:
    while lifecycle.state is not None and (
        lifecycle.state.current_setup_step is not SetupStep.SELECT_SECONDARY_MISSIONS
    ):
        lifecycle.advance_until_decision_or_terminal()


def _choose_secondaries(
    lifecycle: GameLifecycle,
    *,
    player_a_option: str = "tactical",
    player_b_option: str = "fixed:assassination:bring_it_down",
) -> None:
    _advance_to_secondary_mission_step(lifecycle)
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_a_option, result_number=1)

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-b"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_b_option, result_number=2)


def _advance_to_battle(lifecycle: GameLifecycle) -> None:
    _choose_secondaries(lifecycle)
    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            return
        status = lifecycle.advance_until_decision_or_terminal()


def _lifecycle_is_in_battle(lifecycle: GameLifecycle) -> bool:
    return lifecycle.state is not None and lifecycle.state.stage is GameLifecycleStage.BATTLE


def _battle_flow() -> BattleRoundFlow:
    return BattleRoundFlow(
        phase_handlers={
            BattlePhase.COMMAND: CommandPhaseHandler(),
            BattlePhase.MOVEMENT: PlaceholderPhaseHandler(BattlePhase.MOVEMENT),
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.CHARGE: PlaceholderPhaseHandler(BattlePhase.CHARGE),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }
    )


def _battle_state(
    config: GameConfig | None = None,
    *,
    decisions: DecisionController | None = None,
) -> GameState:
    resolved_config = _config() if config is None else config
    state = GameState.from_config(resolved_config)
    for request in resolved_config.army_muster_requests:
        state.record_army_definition(
            muster_army(catalog=resolved_config.army_catalog, request=request)
        )
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="phase9b-battlefield",
            armies=tuple(state.army_definitions),
        ).battlefield_state
    )
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    resolved_decisions = DecisionController() if decisions is None else decisions
    _complete_setup_through_gate(
        state=state,
        decisions=resolved_decisions,
        config=resolved_config,
    )
    return state


def _battle_lifecycle_for_consistency() -> GameLifecycle:
    config = _config()
    decisions = DecisionController()
    state = _battle_state(config, decisions=decisions)
    return GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )


def _phase_state_consistency_payload(
    *,
    phase: BattlePhase,
) -> tuple[GameLifecyclePayload, str, str]:
    lifecycle = _battle_lifecycle_for_consistency()
    state = lifecycle.state
    assert state is not None
    alpha_unit_id = state.army_definitions[0].units[0].unit_instance_id
    beta_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.replace_command_step_state(None)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    if phase is BattlePhase.MOVEMENT:
        state.replace_movement_phase_state(
            MovementPhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
                selected_unit_ids=(alpha_unit_id,),
                moved_unit_ids=(alpha_unit_id,),
            )
        )
    elif phase is BattlePhase.SHOOTING:
        state.replace_shooting_phase_state(
            ShootingPhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
                selected_unit_ids=(alpha_unit_id,),
            )
        )
    elif phase is BattlePhase.CHARGE:
        selection = ChargingUnitSelection(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=alpha_unit_id,
            request_id="phase9b-charge-selection-request",
            result_id="phase9b-charge-selection-result",
        )
        finite_request = DecisionRequest(
            request_id=selection.request_id,
            decision_type="select_charging_unit",
            actor_id=selection.player_id,
            payload={},
            options=(
                DecisionOption(
                    option_id=alpha_unit_id,
                    label="Charge",
                    payload={"unit_instance_id": alpha_unit_id, "take_to_the_skies": False},
                ),
            ),
        )
        lifecycle.decision_controller.request_decision(finite_request)
        lifecycle.decision_controller.submit_result(
            DecisionResult.for_request(
                request=finite_request,
                result_id=selection.result_id,
                selected_option_id=alpha_unit_id,
            )
        )
        roll_request = ChargeRollRequest(
            request_id="phase9b-charge-roll-request",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            unit_instance_id=alpha_unit_id,
            source_decision_request_id=selection.request_id,
            source_decision_result_id=selection.result_id,
        )
        roll_state = DiceRollManager("phase9b-charge-consistency").roll_fixed(
            roll_request.spec,
            [3, 4],
        )
        roll_result = ChargeRollResult.from_roll_state(
            request=roll_request,
            roll_state=roll_state,
            reachable_target_distances_inches={beta_unit_id: 3.0},
        )
        state.replace_charge_phase_state(
            ChargePhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
            )
            .with_unit_selection(selection)
            .with_charge_roll_result(roll_result)
        )
    elif phase is BattlePhase.FIGHT:
        state.replace_fight_phase_state(
            FightPhaseState.start(
                battle_round=state.battle_round,
                active_player_id="player-a",
                policy=lifecycle.config.ruleset_descriptor.fight_policy,
                engaged_at_fight_step_start_unit_ids=(alpha_unit_id, beta_unit_id),
                fights_first_registry=FightsFirstRegistry(),
            )
        )
    else:
        raise AssertionError("Phase consistency fixture requires a non-Command battle phase.")
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    return payload, alpha_unit_id, beta_unit_id


def _complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BattlePhase"]
__all__ += ["BattlePhaseKind", "BattlePhaseSequenceDescriptor", "BattleRoundFlow"]
__all__ += ["ChargePhaseState", "ChargeRollRequest", "ChargeRollResult", "ChargingUnitSelection"]
__all__ += ["DECLINE_STRATAGEM_WINDOW_OPTION_ID", "CommandPhaseHandler"]
__all__ += ["DEFAULT_MAX_LIFECYCLE_TRANSITIONS", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "DiceRollManager"]
__all__ += ["FightPhaseState", "FightsFirstRegistry", "GameConfig", "GameConfigPayload"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecyclePayload", "GameLifecycleStage"]
__all__ += ["GameState", "GameStatePayload", "GeometrySourceKind", "HeightSourceKind"]
__all__ += ["JsonValue", "LifecycleStatus", "LifecycleStatusKind", "MissionSetup"]
__all__ += ["ModelGeometryCatalogRecord", "ModelGeometryCatalogRecordPayload"]
__all__ += ["ModelProfileSelection", "MovementPhaseState", "ObjectiveControlTiming"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "PlaceholderPhaseHandler", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupCompletionGate"]
__all__ += ["SetupSequenceDescriptor", "SetupStep", "SetupStepKind", "ShootingPhaseState"]
__all__ += ["TACTICAL_SECONDARY_DRAW_DECISION_TYPE", "UnitMusterSelection", "WargearSelection"]
__all__ += ["_advance_to_battle", "_advance_to_secondary_mission_step", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_battle_flow", "_battle_lifecycle_for_consistency"]
__all__ += ["_battle_state", "_choose_secondaries", "_complete_setup_through_gate", "_config"]
__all__ += ["_decline_stratagem_window_if_pending", "_descriptor_with_sequences"]
__all__ += ["_lifecycle_is_in_battle", "_mission_setup", "_pending_request"]
__all__ += ["_phase_state_consistency_payload", "_public_secondary_choices", "_request_payload"]
__all__ += ["_start_lifecycle", "_state", "_state_battle_phase", "_submit_pending"]
__all__ += ["accepted_model_geometry", "cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_deterministic_battlefield_scenario", "drain_pending_secondary_mission_setup"]
__all__ += ["ensure_army_mustered_events_for_fixture", "game_lifecycle_stage_from_token"]
__all__ += ["inspect", "json", "lifecycle_status_kind_from_token", "muster_army", "pytest"]
__all__ += ["replace", "seed_completed_fight_phase", "submit_all_deployments_if_pending"]
