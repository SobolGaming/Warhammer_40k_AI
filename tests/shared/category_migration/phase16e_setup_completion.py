from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tests.deployment_submission_helpers import (
    default_deployment_pose,
    submit_all_deployments_if_pending,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import create_empty_deployment_battlefield_state
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import (
    DedicatedTransportSetupConsequence,
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.setup_completion import (
    SetupCompletionGate,
    SetupCompletionViolationCode,
    SetupLegalityReport,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def _advance_to_first_deployment_selection(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16e-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16e-secondary-player-b",
    )
    return lifecycle, deployment_status


def _pre_battle_gate_ready_state() -> GameState:
    config = _config()
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-ready-deploy",
    )
    assert lifecycle.state is not None
    payload = lifecycle.state.to_payload()
    payload["stage"] = GameLifecycleStage.SETUP.value
    payload["setup_step_index"] = len(lifecycle.state.setup_sequence) - 1
    payload["battle_phase_index"] = None
    payload["battle_round"] = 0
    payload["active_player_id"] = None
    payload["command_step_state"] = None
    payload["primary_objective_turn_start_states"] = []
    payload["primary_rules_unit_turn_start_snapshots"] = []
    return GameState.from_payload(payload)


def _state_at_final_setup_step_without_deployments(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=config.army_catalog, request=request))
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    _advance_setup_state_to_step(state, SetupStep.CREATE_BATTLEFIELD)
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    _advance_setup_state_to_step(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    return state


def _dedicated_transport_state_without_transport_reconciliation(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=config.army_catalog, request=request))
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    _advance_setup_state_to_step(state, SetupStep.CREATE_BATTLEFIELD)
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    _advance_setup_state_to_step(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    assert not state.dedicated_transport_setup_consequences
    assert not state.transport_cargo_states
    return state


def _transport_cargo_state(
    *,
    transport_unit_instance_id: str,
    embarked_unit_instance_ids: tuple[str, ...],
) -> TransportCargoState:
    return TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport_unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id="core-transport",
            max_model_count=6,
            allowed_keywords=("Infantry",),
            excluded_keywords=(),
            source_id="transport-capacity:core-transport:6",
        ),
        embarked_unit_instance_ids=embarked_unit_instance_ids,
        phase_battle_round=None,
        started_phase_embarked_unit_instance_ids=embarked_unit_instance_ids,
        disembarked_this_phase_unit_instance_ids=(),
    )


def _place_transport(state: GameState) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    transport_model_id = "army-alpha:transport-unit:core-transport:001"
    state.battlefield_state = battlefield.with_added_unit_placement(
        UnitPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id="army-alpha:transport-unit",
            model_placements=(
                ModelPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id="army-alpha:transport-unit",
                    model_instance_id=transport_model_id,
                    pose=default_deployment_pose(20, "player-a", transport_model_id),
                ),
            ),
        )
    )


def _advance_setup_state_to_step(state: GameState, target_step: SetupStep) -> None:
    while state.current_setup_step is not target_step:
        state.complete_current_setup_step()


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _single_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    matches = [
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    ]
    assert len(matches) == 1
    payload = matches[0]
    assert isinstance(payload, dict)
    return payload


def _payload_object(payload: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = payload[key]
    assert isinstance(value, dict)
    return value


def _violation_codes(report: SetupLegalityReport) -> set[str]:
    return {violation.violation_code.value for violation in report.violations}


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=_army_muster_requests(catalog),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
    )


def _empty_dedicated_transport_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-empty-dedicated-transport",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _transport_roster_request(catalog, embarked_unit_selection_ids=()),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "area-denial",
            "assassination",
            "bring_it_down",
        ),
        mission_setup=_mission_setup(),
    )


def _cargo_dedicated_transport_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-cargo-dedicated-transport",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _transport_roster_request(catalog, embarked_unit_selection_ids=("passenger-unit",)),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "area-denial",
            "assassination",
            "bring_it_down",
        ),
        mission_setup=_mission_setup(),
    )


def _transport_roster_request(
    catalog: ArmyCatalog,
    *,
    embarked_unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    passenger_selections = tuple(
        _unit_selection(unit_selection_id=selection_id)
        for selection_id in embarked_unit_selection_ids
    )
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="take-and-hold",
        unit_selections=(
            *passenger_selections,
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=embarked_unit_selection_ids,
                capacity_profile=DedicatedTransportCapacityProfile(
                    transport_datasheet_id="core-transport",
                    max_model_count=6,
                    allowed_keywords=("Infantry",),
                    excluded_keywords=(),
                    source_id="transport-capacity:core-transport:6",
                ),
                source_id=(
                    "manifest:empty"
                    if not embarked_unit_selection_ids
                    else "manifest:transport-unit"
                ),
            ),
        ),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16e-test")


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
        unit_selections=(_unit_selection(unit_selection_id=unit_selection_id),),
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DedicatedTransportCapacityProfile"]
__all__ += ["DedicatedTransportManifest", "DedicatedTransportSetupConsequence"]
__all__ += ["DetachmentSelection", "DiceExpression", "DiceRollManager", "DiceRollSpec"]
__all__ += ["EventLog", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecyclePayload", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "Path", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SetupCompletionGate", "SetupCompletionViolationCode", "SetupLegalityReport"]
__all__ += ["SetupStep", "TransportCapacityProfile", "TransportCargoState", "UnitMusterSelection"]
__all__ += ["UnitPlacement", "_advance_setup_state_to_step"]
__all__ += ["_advance_to_first_deployment_selection", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_cargo_dedicated_transport_config", "_config"]
__all__ += ["_decision_request", "_dedicated_transport_state_without_transport_reconciliation"]
__all__ += ["_empty_dedicated_transport_config", "_mission_setup", "_payload_object"]
__all__ += ["_place_transport", "_pre_battle_gate_ready_state", "_ruleset"]
__all__ += ["_single_event_payload", "_state_at_final_setup_step_without_deployments"]
__all__ += ["_submit_result", "_transport_cargo_state", "_transport_roster_request"]
__all__ += ["_unit_selection", "_violation_codes", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["default_deployment_pose", "json", "muster_army", "pytest"]
__all__ += ["submit_all_deployments_if_pending"]
