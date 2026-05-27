from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.command import TACTICAL_SECONDARY_DRAW_DECISION_TYPE
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE


@pytest.mark.integration
def test_minimal_catalog_game_reaches_battle_round_one_with_mustered_armies() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = _minimal_two_player_game_config(catalog)
    lifecycle = GameLifecycle()
    lifecycle.start(config)

    first_status = lifecycle.advance_until_decision_or_terminal()

    _assert_secondary_decision(first_status, player_id="player-a")
    state = _require_state(lifecycle)
    assert state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS
    assert state.missing_army_player_ids() == ()
    _assert_datasheet_backed_army(state, player_id="player-a")
    _assert_datasheet_backed_army(state, player_id="player-b")

    second_status = _submit_result(
        lifecycle,
        status=first_status,
        option_id="tactical",
        result_id="phase9d-result-000001",
    )
    _assert_secondary_decision(second_status, player_id="player-b")

    command_status = _submit_result(
        lifecycle,
        status=second_status,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase9d-result-000002",
    )

    state = _require_state(lifecycle)
    assert state.stage is GameLifecycleStage.BATTLE
    assert state.battle_round == 1
    assert state.active_player_id == "player-a"
    assert state.current_battle_phase is BattlePhase.COMMAND
    _assert_hidden_secondaries_do_not_leak(state)
    assert command_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert command_status.decision_request is not None
    assert command_status.decision_request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    assert command_status.decision_request.actor_id == "player-a"

    placeholder_status = _submit_result(
        lifecycle,
        status=command_status,
        option_id="draw",
        result_id="phase9d-result-000003",
    )

    state = _require_state(lifecycle)
    assert placeholder_status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert placeholder_status.payload == {
        "completed_phase": BattlePhase.MOVEMENT.value,
        "phase_body_status": "placeholder_noop",
        "battle_round": 1,
        "active_player_id": "player-a",
        "current_phase": BattlePhase.SHOOTING.value,
    }
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert len(state.tactical_secondary_draws) == 1
    assert state.tactical_secondary_draws[0].player_id == "player-a"
    assert state.tactical_secondary_draws[0].battle_round == 1
    assert state.tactical_secondary_draws[0].draw_count == 2

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    payload_blob = json.dumps(payload, sort_keys=True)
    assert "<" not in payload_blob
    assert "object at 0x" not in payload_blob
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def _minimal_two_player_game_config(catalog: ArmyCatalog) -> GameConfig:
    return GameConfig(
        game_id="phase9d-smoke-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth(
            descriptor_version="core-v2-phase9d-smoke"
        ),
        army_catalog=catalog,
        army_muster_requests=(
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
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
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
            detachment_id="core-combined-arms",
        ),
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
            ),
        ),
    )


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    request = status.decision_request
    assert request is not None
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _assert_secondary_decision(status: LifecycleStatus, *, player_id: str) -> None:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert status.decision_request.actor_id == player_id


def _require_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _assert_datasheet_backed_army(state: GameState, *, player_id: str) -> None:
    army = state.army_definition_for_player(player_id)
    assert army is not None
    _assert_datasheet_backed_infantry(army)


def _assert_datasheet_backed_infantry(army: ArmyDefinition) -> None:
    assert army.catalog_id == "phase9a-canonical"
    assert army.ruleset_id.version == "core-v2-phase9a"
    assert army.detachment_selection.faction_id == "core-marine-force"
    assert army.detachment_selection.detachment_id == "core-combined-arms"

    unit = army.units[0]
    model = unit.own_models[0]
    characteristics = {value.characteristic: value.final for value in model.characteristics}

    assert unit.datasheet_id == "core-intercessor-like-infantry"
    assert unit.datasheet_source_ids == ("datasheet:core-intercessor-like-infantry",)
    assert unit.wargear_selections[0].wargear_ids == ("core-bolt-rifle",)
    assert len(unit.own_models) == 5
    assert model.datasheet_id == unit.datasheet_id
    assert model.model_profile_id == "core-intercessor-like"
    assert model.base_size.diameter_mm == 32.0
    assert characteristics[Characteristic.MOVEMENT] == 6
    assert characteristics[Characteristic.OBJECTIVE_CONTROL] == 2
    assert characteristics[Characteristic.BALLISTIC_SKILL] == 3
    assert model.starting_wounds == 2
    assert model.wounds_remaining == 2
    assert model.source_ids == (
        "datasheet:core-intercessor-like-infantry",
        "datasheet:core-intercessor-like-infantry:profile",
    )


def _assert_hidden_secondaries_do_not_leak(state: GameState) -> None:
    player_a_public_payload = state.to_public_payload(viewer_player_id="player-a")
    player_a_blob = json.dumps(player_a_public_payload, sort_keys=True)
    secondary_choices = player_a_public_payload["secondary_mission_choices"]
    assert isinstance(secondary_choices, list)

    assert "assassination" not in player_a_blob
    assert "bring_it_down" not in player_a_blob
    assert any(
        choice
        == {
            "player_id": "player-b",
            "selected": True,
            "hidden": True,
        }
        for choice in secondary_choices
    )
