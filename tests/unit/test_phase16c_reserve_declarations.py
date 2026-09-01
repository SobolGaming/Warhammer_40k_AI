from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.adapters.access_control import (
    AuthenticatedPrincipal,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.adapters.redaction import (
    battle_formation_declarations_are_unresolved,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, SetupSequenceDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
    BattleFormationDeclarationState,
    ReserveDeclarationAction,
    ReserveDeclarationRequest,
    ReserveDeclarationSelection,
    ReserveLegalityContext,
    ReserveLegalityReport,
    apply_mandatory_aircraft_reserve_declarations,
    invalid_reserve_declaration_status,
    reserve_declaration_action_from_token,
    reserve_declaration_options_for_player,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    ReserveUnitPointValue,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_phase16c_strategic_reserve_declaration_uses_lifecycle_decision_path() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)

    assert request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["secret"] is True
    assert _option_ids(request) == (
        "complete_reserve_declarations",
        "declare_strategic_reserves:army-alpha:reserve-unit",
    )

    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-strategic-result",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )
    assert lifecycle.state is not None
    reserve_state = lifecycle.state.reserve_state_for_unit("army-alpha:reserve-unit")
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS
    assert reserve_state.declared_during_step == SetupStep.DECLARE_BATTLE_FORMATIONS.value
    assert reserve_state.source_rule_ids == ("strategic_reserves",)
    assert reserve_state.points_contribution == 400

    record_payloads = [
        record.to_payload()
        for record in lifecycle.decision_controller.records
        if record.request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    ]
    encoded = json.dumps(record_payloads, sort_keys=True)
    assert " object at 0x" not in encoded
    assert "ReserveState(" not in encoded

    deployment_request = _decision_request(deployment_status)
    assert deployment_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert deployment_request.actor_id == "player-b"
    assert _option_ids(deployment_request) == ("deploy:army-beta:intercessor-unit-2",)
    terminal_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16c-strategic-deploy",
    )
    assert terminal_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    }


def test_phase16c_declarations_are_private_until_public_reveal() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)

    assert lifecycle.state is not None
    reserve_model_id = next(
        model.model_instance_id
        for army in lifecycle.state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:reserve-unit"
        for model in unit.own_models
    )
    assert lifecycle.state.battlefield_state is not None
    pristine_battlefield = lifecycle.state.battlefield_state
    lifecycle.state.replace_battlefield_state(
        pristine_battlefield.with_added_unit_placement(
            UnitPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id="army-alpha:reserve-unit",
                model_placements=(
                    ModelPlacement(
                        army_id="army-alpha",
                        player_id="player-a",
                        unit_instance_id="army-alpha:reserve-unit",
                        model_instance_id=reserve_model_id,
                        pose=Pose.at(4.0, 5.0),
                    ),
                ),
            )
        )
    )
    player_a_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-a")
    player_b_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    administrator = AuthenticatedPrincipal(
        principal_id="phase16c-admin",
        role=PrincipalRole.ADMINISTRATOR,
    ).bind_to_session(player_ids=lifecycle.state.player_ids)
    admin_view = project_game_view(lifecycle=lifecycle, viewer=administrator)
    assert "army-alpha:reserve-unit" in player_a_view["unit_display_by_id"]
    assert "army-alpha:reserve-unit" in player_b_view["unit_display_by_id"]
    assert player_a_view["pending_decision"] is not None
    assert player_a_view["pending_decision"]["decision_type"] == (
        SELECT_RESERVE_DECLARATION_DECISION_TYPE
    )
    assert player_b_view["pending_decision"] is not None
    assert player_b_view["pending_decision"]["decision_type"] == "hidden_decision"

    owner_models = player_a_view["battlefield_view"]
    opponent_models = player_b_view["battlefield_view"]
    admin_models = admin_view["battlefield_view"]
    assert owner_models is not None
    assert opponent_models is not None
    assert admin_models is not None
    assert owner_models["authoritative"]["models_by_id"][reserve_model_id]["state"] == "placed"
    assert owner_models["authoritative"]["models_by_id"][reserve_model_id]["pose"] is not None
    assert opponent_models["authoritative"]["models_by_id"][reserve_model_id]["state"] == (
        "undeployed"
    )
    assert opponent_models["authoritative"]["models_by_id"][reserve_model_id]["pose"] is None
    assert admin_models["authoritative"]["models_by_id"][reserve_model_id]["state"] == "placed"
    owner_battlefield_state = player_a_view["battlefield_state"]
    opponent_battlefield_state = player_b_view["battlefield_state"]
    admin_battlefield_state = admin_view["battlefield_state"]
    assert isinstance(owner_battlefield_state, dict)
    assert isinstance(opponent_battlefield_state, dict)
    assert isinstance(admin_battlefield_state, dict)
    owner_placed_armies = owner_battlefield_state["placed_armies"]
    opponent_placed_armies = opponent_battlefield_state["placed_armies"]
    admin_placed_armies = admin_battlefield_state["placed_armies"]
    assert isinstance(owner_placed_armies, list)
    assert isinstance(opponent_placed_armies, list)
    assert isinstance(admin_placed_armies, list)
    assert len(owner_placed_armies) == 1
    assert opponent_placed_armies == []
    assert len(admin_placed_armies) == 1
    lifecycle.state.replace_battlefield_state(pristine_battlefield)

    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-private-declaration",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )
    assert deployment_status.decision_request is not None
    owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    opponent_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    admin_events = EventStreamCursor().events_since_for_context(
        lifecycle.decision_controller.event_log,
        viewer=administrator,
    )
    assert any(event["event_type"] == "reserve_unit_declared" for event in owner_events["events"])
    assert not any(
        event["event_type"] == "reserve_unit_declared" for event in opponent_events["events"]
    )
    assert any(event["event_type"] == "reserve_unit_declared" for event in admin_events["events"])
    reveal_event = next(
        event
        for event in opponent_events["events"]
        if event["event_type"] == "battle_formations_revealed"
    )
    reveal_payload = reveal_event["payload"]
    assert isinstance(reveal_payload, dict)
    revealed_reserve_state = lifecycle.state.reserve_state_for_unit("army-alpha:reserve-unit")
    assert revealed_reserve_state is not None
    assert reveal_payload["reserve_states"] == [revealed_reserve_state.to_payload()]

    player_b_revealed = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    revealed_battlefield = player_b_revealed["battlefield_view"]
    assert revealed_battlefield is not None
    revealed_model = revealed_battlefield["authoritative"]["models_by_id"][reserve_model_id]
    assert revealed_model["state"] == "reserves"
    assert revealed_model["state_context"]["reserve_kind"] == "strategic_reserves"


def test_phase16c_formation_projection_is_private_from_creation_through_declaration() -> None:
    config = _battle_formation_aggregate_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    assert lifecycle.state is not None
    administrator = AuthenticatedPrincipal(
        principal_id="phase16c-boundary-admin",
        role=PrincipalRole.ADMINISTRATOR,
    ).bind_to_session(player_ids=lifecycle.state.player_ids)

    assert battle_formation_declarations_are_unresolved(lifecycle.state) is True
    pre_muster_views = (
        project_game_view(lifecycle=lifecycle, viewer_player_id="player-a"),
        project_game_view(lifecycle=lifecycle, viewer_player_id="player-b"),
        project_game_view(lifecycle=lifecycle, viewer=administrator),
    )
    assert [view["unit_display_by_id"] for view in pre_muster_views] == [{}, {}, {}]

    status = lifecycle.advance_until_decision_or_terminal()
    _assert_current_setup_step(lifecycle.state, SetupStep.SELECT_SECONDARY_MISSIONS)
    assert battle_formation_declarations_are_unresolved(lifecycle.state) is True
    assert lifecycle.state.transport_cargo_states
    assert lifecycle.state.dedicated_transport_setup_consequences
    assert lifecycle.state.starting_attached_unit_records
    expected_attachment_records = [
        record.to_payload()
        for record in lifecycle.state.starting_attached_unit_records
        if record.player_id == "player-a"
    ]
    public_muster_attachment_payloads: list[JsonValue] = []
    for event_view in (
        EventStreamCursor().events_since(
            lifecycle.decision_controller.event_log,
            viewer_player_id="player-a",
        ),
        EventStreamCursor().events_since(
            lifecycle.decision_controller.event_log,
            viewer_player_id="player-b",
        ),
        EventStreamCursor().events_since_for_context(
            lifecycle.decision_controller.event_log,
            viewer=administrator,
        ),
    ):
        army_mustered_payload = next(
            event["payload"]
            for event in event_view["events"]
            if event["event_type"] == "army_mustered"
            and isinstance(event["payload"], dict)
            and event["payload"]["player_id"] == "player-a"
        )
        assert isinstance(army_mustered_payload, dict)
        public_muster_attachment_payloads.append(
            army_mustered_payload["starting_attached_unit_records"]
        )
    assert public_muster_attachment_payloads == [expected_attachment_records] * 3

    bodyguard_model_id = next(
        model.model_instance_id
        for army in lifecycle.state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:bodyguard-unit"
        for model in unit.own_models
    )
    _assert_opponent_formation_state_is_hidden(
        lifecycle=lifecycle,
        administrator=administrator,
        model_instance_id=bodyguard_model_id,
    )
    _assert_opponent_premature_placement_is_hidden(
        lifecycle=lifecycle,
        administrator=administrator,
        unit_instance_id="army-alpha:reserve-unit",
    )

    result_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        request = status.decision_request
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase16c-boundary-secondary-{result_index:02d}",
                request=request,
                selected_option_id="tactical",
            )
        )
        result_index += 1

    request = _decision_request(status)
    assert request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    _assert_current_setup_step(lifecycle.state, SetupStep.DECLARE_BATTLE_FORMATIONS)
    assert battle_formation_declarations_are_unresolved(lifecycle.state) is True
    _assert_opponent_formation_state_is_hidden(
        lifecycle=lifecycle,
        administrator=administrator,
        model_instance_id=bodyguard_model_id,
    )

    lifecycle.state.record_faction_rule_state(
        FactionRuleState(
            state_id="phase16c-battle-formation-choice",
            player_id="player-a",
            faction_id="core-marine-force",
            source_rule_id="phase16c-battle-formation-rule",
            state_kind="phase16c-test-choice",
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase16c-battle-formation-request",
            result_id="phase16c-battle-formation-result",
            payload={"choice": "alpha"},
        )
    )
    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-boundary-reserve-result",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )
    assert deployment_status.decision_request is not None
    assert battle_formation_declarations_are_unresolved(lifecycle.state) is False

    expected_reveal_payload = {
        "game_id": lifecycle.state.game_id,
        "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        "player_ids": list(lifecycle.state.player_ids),
        "reserve_states": [
            reserve.to_payload()
            for reserve in sorted(
                lifecycle.state.reserve_states,
                key=lambda reserve: (reserve.player_id, reserve.unit_instance_id),
            )
            if reserve.declared_during_step == SetupStep.DECLARE_BATTLE_FORMATIONS.value
        ],
        "transport_cargo_states": [
            cargo.to_payload()
            for cargo in sorted(
                lifecycle.state.transport_cargo_states,
                key=lambda cargo: (cargo.player_id, cargo.transport_unit_instance_id),
            )
            if cargo.embarked_unit_instance_ids
        ],
        "dedicated_transport_setup_consequences": [
            consequence.to_payload()
            for consequence in sorted(
                lifecycle.state.dedicated_transport_setup_consequences,
                key=lambda consequence: (
                    consequence.player_id,
                    consequence.transport_unit_instance_id,
                ),
            )
        ],
        "faction_rule_states": [
            faction_state.to_payload()
            for faction_state in sorted(
                lifecycle.state.faction_rule_states,
                key=lambda faction_state: (faction_state.player_id, faction_state.state_id),
            )
            if faction_state.setup_step is SetupStep.DECLARE_BATTLE_FORMATIONS
        ],
    }
    assert all(
        expected_reveal_payload[field]
        for field in (
            "reserve_states",
            "transport_cargo_states",
            "dedicated_transport_setup_consequences",
            "faction_rule_states",
        )
    )

    reveal_payloads: list[JsonValue] = []
    for event_view in (
        EventStreamCursor().events_since(
            lifecycle.decision_controller.event_log,
            viewer_player_id="player-a",
        ),
        EventStreamCursor().events_since(
            lifecycle.decision_controller.event_log,
            viewer_player_id="player-b",
        ),
        EventStreamCursor().events_since_for_context(
            lifecycle.decision_controller.event_log,
            viewer=administrator,
        ),
    ):
        reveal_payloads.append(
            next(
                event["payload"]
                for event in event_view["events"]
                if event["event_type"] == "battle_formations_revealed"
            )
        )
    assert reveal_payloads == [expected_reveal_payload] * 3

    revealed_views = (
        project_game_view(lifecycle=lifecycle, viewer_player_id="player-a"),
        project_game_view(lifecycle=lifecycle, viewer_player_id="player-b"),
        project_game_view(lifecycle=lifecycle, viewer=administrator),
    )
    revealed_model_states: list[str] = []
    for view in revealed_views:
        battlefield = view["battlefield_view"]
        assert battlefield is not None
        revealed_model_states.append(
            battlefield["authoritative"]["models_by_id"][bodyguard_model_id]["state"]
        )
    assert revealed_model_states == ["embarked", "embarked", "embarked"]

    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16c-boundary-deployment",
    )
    round_tripped = GameLifecycle.from_payload(lifecycle.to_payload())
    assert round_tripped.state is not None
    assert [record.to_payload() for record in round_tripped.state.reserve_states] == [
        record.to_payload() for record in lifecycle.state.reserve_states
    ]
    assert [record.to_payload() for record in round_tripped.state.transport_cargo_states] == [
        record.to_payload() for record in lifecycle.state.transport_cargo_states
    ]
    assert [
        record.to_payload() for record in round_tripped.state.starting_attached_unit_records
    ] == [record.to_payload() for record in lifecycle.state.starting_attached_unit_records]
    assert [
        record.to_payload() for record in round_tripped.state.dedicated_transport_setup_consequences
    ] == [record.to_payload() for record in lifecycle.state.dedicated_transport_setup_consequences]
    assert [record.to_payload() for record in round_tripped.state.faction_rule_states] == [
        record.to_payload() for record in lifecycle.state.faction_rule_states
    ]


def test_phase16c_opponent_projection_hides_mutable_model_wounds_until_reveal() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_battle_formation_aggregate_config())
    lifecycle.advance_until_decision_or_terminal()
    state = lifecycle.state
    assert state is not None
    assert battle_formation_declarations_are_unresolved(state) is True

    owner_army = state.army_definition_for_player("player-a")
    assert owner_army is not None
    transport = owner_army.unit_by_id("army-alpha:empty-transport")
    (transport_model,) = transport.own_models
    current_wounds = transport_model.starting_wounds - 3
    wounded_transport = replace(
        transport,
        own_models=(replace(transport_model, wounds_remaining=current_wounds),),
    )
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    wounded_transport if unit == transport else unit for unit in army.units
                ),
            )
            if army.player_id == owner_army.player_id
            else army
            for army in state.army_definitions
        ]
    )

    administrator = AuthenticatedPrincipal(
        principal_id="phase16c-mutable-state-admin",
        role=PrincipalRole.ADMINISTRATOR,
    ).bind_to_session(player_ids=state.player_ids)
    owner_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-a")
    opponent_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    admin_view = project_game_view(lifecycle=lifecycle, viewer=administrator)
    model_id = transport_model.model_instance_id

    assert owner_view["model_display_by_id"][model_id]["wounds_remaining"] == current_wounds
    assert admin_view["model_display_by_id"][model_id]["wounds_remaining"] == current_wounds
    assert opponent_view["model_display_by_id"][model_id]["wounds_remaining"] == (
        transport_model.starting_wounds
    )
    opponent_battlefield = opponent_view["battlefield_view"]
    assert opponent_battlefield is not None
    assert opponent_battlefield["authoritative"]["models_by_id"][model_id]["state"] == (
        "undeployed"
    )


def test_phase16c_absent_declare_battle_formations_step_has_no_secrecy_window() -> None:
    ruleset = _ruleset()
    ruleset_without_declarations = replace(
        ruleset,
        setup_sequence=SetupSequenceDescriptor(
            steps=tuple(
                step
                for step in ruleset.setup_sequence.steps
                if step is not SetupStep.DECLARE_BATTLE_FORMATIONS
            )
        ),
        descriptor_hash="",
    )
    state = GameState.from_config(
        replace(_config(), ruleset_descriptor=ruleset_without_declarations)
    )

    assert battle_formation_declarations_are_unresolved(state) is False


def test_phase16c_deep_strike_declaration_creates_deep_strike_reserve_state() -> None:
    config = _config(
        player_a_unit_selections=(
            _unit_selection(
                unit_selection_id="deep-strike-unit",
                datasheet_id="core-deep-strike-unit",
                model_profile_id="core-deep-strike-model",
                model_count=3,
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)

    assert _option_ids(request) == (
        "complete_reserve_declarations",
        "declare_deep_strike:army-alpha:deep-strike-unit",
    )
    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-deep-strike-result",
            request=request,
            selected_option_id="declare_deep_strike:army-alpha:deep-strike-unit",
        )
    )

    assert lifecycle.state is not None
    reserve_state = lifecycle.state.reserve_state_for_unit("army-alpha:deep-strike-unit")
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE
    assert reserve_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS
    assert reserve_state.source_rule_ids == ("deep_strike",)
    assert reserve_state.points_contribution == 0

    deployment_request = _decision_request(deployment_status)
    assert deployment_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert deployment_request.actor_id == "player-b"


def test_phase16c_deep_strike_declaration_accepts_core_ability_without_keyword() -> None:
    config = _config(
        catalog=_catalog_with_datasheet_keywords({"core-deep-strike-unit": ("Infantry",)}),
        player_a_unit_selections=(
            _unit_selection(
                unit_selection_id="deep-strike-unit",
                datasheet_id="core-deep-strike-unit",
                model_profile_id="core-deep-strike-model",
                model_count=3,
            ),
        ),
    )
    _lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)

    assert _option_ids(request) == (
        "complete_reserve_declarations",
        "declare_deep_strike:army-alpha:deep-strike-unit",
    )


def test_phase16c_completion_option_records_event_without_state_mutation() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)

    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-completion-result",
            request=request,
            selected_option_id="complete_reserve_declarations",
        )
    )

    assert lifecycle.state is not None
    assert lifecycle.state.reserve_state_for_unit("army-alpha:reserve-unit") is None
    completion_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "reserve_declarations_completed"
    )
    assert len(completion_events) == 1
    assert isinstance(completion_events[0].payload, dict)
    assert completion_events[0].payload["player_id"] == "player-a"
    assert completion_events[0].payload["source_decision_request_id"] == request.request_id

    deployment_request = _decision_request(deployment_status)
    assert deployment_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert deployment_request.actor_id == "player-b"


def test_phase16c_invalid_stale_reserve_declaration_rejects_before_queue_pop() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)
    assert lifecycle.state is not None
    lifecycle.state.complete_current_setup_step()

    invalid_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-stale-result",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(invalid_status.payload, dict)
    assert invalid_status.payload["invalid_reason"] == "reserve_declaration_request_drift"
    assert invalid_status.payload["field"] == "setup_step"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.state.reserve_state_for_unit("army-alpha:reserve-unit") is None


def test_phase16c_invalid_submission_reports_option_and_payload_drift() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)
    assert lifecycle.state is not None
    result = DecisionResult.for_request(
        result_id="phase16c-now-illegal-result",
        request=request,
        selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
    )
    lifecycle.state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id="army-alpha:reserve-unit",
            reserve_kind=ReserveKind.DEEP_STRIKE,
            source_rule_ids=("deep_strike",),
        )
    )

    option_drift_status = invalid_reserve_declaration_status(
        state=lifecycle.state,
        config=config,
        request=request,
        result=result,
    )
    assert option_drift_status is not None
    assert option_drift_status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(option_drift_status.payload, dict)
    assert option_drift_status.payload["invalid_reason"] == "reserve_declaration_request_drift"
    assert option_drift_status.payload["field"] == "selected_option_id"

    payload_lifecycle, payload_reserve_status = _advance_to_reserve_request(config)
    payload_request = _decision_request(payload_reserve_status)
    assert payload_lifecycle.state is not None
    payload_result = DecisionResult.for_request(
        result_id="phase16c-payload-drift-result",
        request=payload_request,
        selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
    )
    changed_source_config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="changed-points:army-alpha:reserve-unit",
            ),
        ),
    )

    payload_drift_status = invalid_reserve_declaration_status(
        state=payload_lifecycle.state,
        config=changed_source_config,
        request=payload_request,
        result=payload_result,
    )
    assert payload_drift_status is not None
    assert payload_drift_status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(payload_drift_status.payload, dict)
    assert payload_drift_status.payload["invalid_reason"] == "reserve_declaration_request_drift"
    assert payload_drift_status.payload["field"] == "payload"


def test_phase16c_strategic_cap_and_fortifications_are_not_declared() -> None:
    config = _config(
        catalog=_catalog_with_datasheet_keywords(
            {
                "core-vehicle-monster": ("Fortification", "Vehicle"),
            }
        ),
        player_a_unit_selections=(
            _unit_selection(unit_selection_id="over-cap-unit"),
            _unit_selection(
                unit_selection_id="fortification-unit",
                datasheet_id="core-vehicle-monster",
                model_profile_id="core-vehicle-monster",
                model_count=1,
            ),
        ),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:over-cap-unit",
                points=1001,
                source_id="test-points:army-alpha:over-cap-unit",
            ),
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:fortification-unit",
                points=400,
                source_id="test-points:army-alpha:fortification-unit",
            ),
        ),
    )
    state = _state_at_declare_battle_formations(config)
    options = reserve_declaration_options_for_player(
        state=state,
        config=config,
        player_id="player-a",
        include_completion=True,
    )

    assert _option_ids_from_options(options) == ("complete_reserve_declarations",)


def test_phase16c_reserve_declaration_payload_objects_are_fail_fast() -> None:
    point_value = ReserveUnitPointValue(
        unit_instance_id="army-alpha:reserve-unit",
        points=400,
        source_id="test-points:army-alpha:reserve-unit",
    )
    context = ReserveLegalityContext(
        player_id="player-a",
        battle_size_points_limit=2000,
        strategic_reserves_points_limit=1000,
        current_strategic_reserves_points=400,
        unit_points=(point_value,),
    )
    assert context.points_for_unit("army-alpha:reserve-unit") == point_value
    assert context.points_for_unit("army-alpha:unknown-unit") is None
    assert context.to_payload()["unit_points"][0]["source_id"] == point_value.source_id

    declaration_state = BattleFormationDeclarationState(
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        next_player_id="player-a",
        available_declaration_count_by_player={"player-a": 1, "player-b": 0},
        completed_player_ids=("player-b",),
    )
    assert declaration_state.to_payload() == {
        "setup_step": "declare_battle_formations",
        "next_player_id": "player-a",
        "available_declaration_count_by_player": {"player-a": 1, "player-b": 0},
        "completed_player_ids": ["player-b"],
    }

    request_context = ReserveDeclarationRequest(
        request_id="reserve-request-1",
        actor_id="player-a",
        game_id="phase16c-game",
        player_id="player-a",
        ruleset_descriptor_hash="phase16c-ruleset",
        strategic_reserves_points_limit=1000,
        current_strategic_reserves_points=0,
        available_declaration_count=1,
    )
    completion_selection = ReserveDeclarationSelection(
        submission_kind=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        action_kind=ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS,
        game_id="phase16c-game",
        player_id="player-a",
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        ruleset_descriptor_hash="phase16c-ruleset",
        reserve_origin=None,
        reserve_kind=None,
        source_rule_id=None,
        unit_instance_id=None,
        unit_points=0,
        embarked_unit_points=0,
        strategic_reserves_points_limit=1000,
        current_strategic_reserves_points=0,
        points_after_declaration=0,
        points_contribution=0,
        embarked_unit_instance_ids=(),
        source_ids=(),
    )
    decision_request = request_context.to_decision_request(
        (
            DecisionOption(
                option_id="complete_reserve_declarations",
                label="Complete Reserve Declarations",
                payload=validate_json_value(completion_selection.to_payload()),
            ),
        )
    )
    assert (
        ReserveDeclarationRequest.from_decision_request_payload(decision_request.payload)
        == request_context
    )
    assert (
        ReserveDeclarationSelection.from_payload(completion_selection.to_payload())
        == completion_selection
    )
    assert ReserveLegalityReport(
        is_legal=False,
        violation_codes=("over_cap",),
        message="over cap",
    ).to_payload() == {
        "is_legal": False,
        "violation_codes": ["over_cap"],
        "message": "over cap",
    }
    assert (
        reserve_declaration_action_from_token("complete_reserve_declarations")
        is ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS
    )

    with pytest.raises(GameLifecycleError, match="current points exceed limit"):
        ReserveLegalityContext(
            player_id="player-a",
            battle_size_points_limit=2000,
            strategic_reserves_points_limit=1000,
            current_strategic_reserves_points=1001,
            unit_points=(point_value,),
        )
    with pytest.raises(GameLifecycleError, match="legal result cannot have violations"):
        ReserveLegalityReport(is_legal=True, violation_codes=("over_cap",))
    with pytest.raises(GameLifecycleError, match="missing request"):
        ReserveDeclarationRequest.from_decision_request_payload({})
    with pytest.raises(GameLifecycleError, match="completion selection must not set unit"):
        ReserveDeclarationSelection(
            submission_kind=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
            action_kind=ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS,
            game_id="phase16c-game",
            player_id="player-a",
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            ruleset_descriptor_hash="phase16c-ruleset",
            reserve_origin=None,
            reserve_kind=None,
            source_rule_id=None,
            unit_instance_id="army-alpha:reserve-unit",
            unit_points=0,
            embarked_unit_points=0,
            strategic_reserves_points_limit=1000,
            current_strategic_reserves_points=0,
            points_after_declaration=0,
            points_contribution=0,
            embarked_unit_instance_ids=(),
            source_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="requires reserve context"):
        ReserveDeclarationSelection(
            submission_kind=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
            action_kind=ReserveDeclarationAction.DECLARE_RESERVE,
            game_id="phase16c-game",
            player_id="player-a",
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            ruleset_descriptor_hash="phase16c-ruleset",
            reserve_origin=None,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            source_rule_id="strategic_reserves",
            unit_instance_id="army-alpha:reserve-unit",
            unit_points=400,
            embarked_unit_points=0,
            strategic_reserves_points_limit=1000,
            current_strategic_reserves_points=0,
            points_after_declaration=400,
            points_contribution=400,
            embarked_unit_instance_ids=(),
            source_ids=("test-points:army-alpha:reserve-unit",),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveDeclarationAction token"):
        reserve_declaration_action_from_token("unsupported")


def test_phase16c_aircraft_are_mandatory_source_backed_reserves() -> None:
    config = _config(
        catalog=_catalog_with_datasheet_keywords(
            {
                "core-vehicle-monster": ("Aircraft", "Fly", "Vehicle"),
            }
        ),
        player_a_unit_selections=(
            _unit_selection(
                unit_selection_id="aircraft-unit",
                datasheet_id="core-vehicle-monster",
                model_profile_id="core-vehicle-monster",
                model_count=1,
            ),
        ),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:aircraft-unit",
                points=300,
                source_id="test-points:army-alpha:aircraft-unit",
            ),
        ),
    )
    lifecycle, deployment_status = _advance_to_deployment_or_later(config)

    assert lifecycle.state is not None
    reserve_state = lifecycle.state.reserve_state_for_unit("army-alpha:aircraft-unit")
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.AIRCRAFT_MANDATORY_RESERVE
    assert reserve_state.source_rule_ids == ("aircraft_mandatory_reserve",)
    assert reserve_state.points_contribution == 300
    assert reserve_state.status is ReserveStatus.IN_RESERVES

    deployment_request = _decision_request(deployment_status)
    assert deployment_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert deployment_request.actor_id == "player-b"
    assert _option_ids(deployment_request) == ("deploy:army-beta:intercessor-unit-2",)
    owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    opponent_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    assert any(
        event["event_type"] == "aircraft_reserve_declared" for event in owner_events["events"]
    )
    assert not any(
        event["event_type"] == "aircraft_reserve_declared" for event in opponent_events["events"]
    )
    reveal_payload = next(
        event["payload"]
        for event in opponent_events["events"]
        if event["event_type"] == "battle_formations_revealed"
    )
    assert isinstance(reveal_payload, dict)
    assert reveal_payload["reserve_states"] == [reserve_state.to_payload()]


def test_phase16c_reserve_declaration_payloads_round_trip_through_lifecycle_payload() -> None:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)
    pending_payload = lifecycle.to_payload()
    restored_pending = GameLifecycle.from_payload(pending_payload)

    restored_request = restored_pending.decision_controller.queue.peek_next()
    assert restored_request.to_payload() == request.to_payload()
    assert isinstance(restored_request.payload, dict)
    assert restored_request.payload["secret"] is True

    after_declaration = restored_pending.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-round-trip-result",
            request=restored_pending.decision_controller.queue.peek_next(),
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )
    declared_payload = restored_pending.to_payload()
    restored_declared = GameLifecycle.from_payload(declared_payload)

    assert (
        _decision_request(after_declaration).decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    )
    assert restored_declared.state is not None
    reserve_state = restored_declared.state.reserve_state_for_unit("army-alpha:reserve-unit")
    assert reserve_state is not None
    assert reserve_state.points_contribution == 400
    assert reserve_state.source_rule_ids == ("strategic_reserves",)
    restored_event_types = tuple(
        event.event_type for event in restored_declared.decision_controller.event_log.records
    )
    assert "reserve_unit_declared" in restored_event_types
    assert "battle_formations_revealed" in restored_event_types
    reserve_event = next(
        event
        for event in restored_declared.decision_controller.event_log.records
        if event.event_type == "reserve_unit_declared"
    )
    assert isinstance(reserve_event.payload, dict)
    assert reserve_event.payload["secret"] is True
    assert reserve_event.payload["visibility_source"] == (SetupStep.DECLARE_BATTLE_FORMATIONS.value)

    missing_source_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(declared_payload, sort_keys=True)),
    )
    missing_source_event = next(
        event
        for event in missing_source_payload["decisions"]["event_log"]
        if event["event_type"] == "reserve_unit_declared"
    )
    missing_source_event["event_type"] = "phase16c_removed_reserve_declaration"
    with pytest.raises(
        GameLifecycleError,
        match="Initial reserve declaration evidence drift",
    ):
        GameLifecycle.from_payload(missing_source_payload)

    duplicate_source_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(declared_payload, sort_keys=True)),
    )
    duplicate_events = duplicate_source_payload["decisions"]["event_log"]
    source_event = next(
        event for event in duplicate_events if event["event_type"] == "reserve_unit_declared"
    )
    duplicate_events.append(
        {
            "event_id": f"event-{len(duplicate_events) + 1:06d}",
            "event_type": source_event["event_type"],
            "payload": json.loads(json.dumps(source_event["payload"], sort_keys=True)),
        }
    )
    with pytest.raises(GameLifecycleError, match="Initial reserve declaration evidence drift"):
        GameLifecycle.from_payload(duplicate_source_payload)

    forged_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(declared_payload, sort_keys=True)),
    )
    forged_declaration_event = next(
        event
        for event in forged_payload["decisions"]["event_log"]
        if event["event_type"] == "reserve_unit_declared"
    )
    assert isinstance(forged_declaration_event["payload"], dict)
    forged_reserve_state = forged_declaration_event["payload"]["reserve_state"]
    assert isinstance(forged_reserve_state, dict)
    forged_policy = forged_reserve_state["destruction_deadline_policy"]
    assert isinstance(forged_policy, dict)
    forged_policy["source_id"] = "phase16c:forged:reserve-deadline-policy"

    with pytest.raises(GameLifecycleError, match="Initial reserve declaration evidence drift"):
        GameLifecycle.from_payload(forged_payload)


def test_phase16c_restore_rejects_living_reserve_model_marked_removed() -> None:
    lifecycle, reserve_model_id = _declared_strategic_reserve_lifecycle()
    state = lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    assert reserve_model_id not in battlefield.placed_model_ids()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    state_payload = payload["state"]
    assert isinstance(state_payload, dict)
    battlefield_payload = state_payload["battlefield_state"]
    assert isinstance(battlefield_payload, dict)
    removed_model_ids = battlefield_payload["removed_model_ids"]
    assert isinstance(removed_model_ids, list)
    removed_model_ids.append(reserve_model_id)

    with pytest.raises(
        GameLifecycleError,
        match="living unarrived reserve models must not be removed",
    ):
        GameLifecycle.from_payload(payload)


def test_phase16c_restore_rejects_dead_reserve_model_not_marked_removed() -> None:
    lifecycle, reserve_model_id = _declared_strategic_reserve_lifecycle()
    state = lifecycle.state
    assert state is not None
    _replace_model_wounds_remaining(
        state=state,
        model_instance_id=reserve_model_id,
        wounds_remaining=0,
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    assert reserve_model_id not in battlefield.placed_model_ids()
    assert reserve_model_id not in battlefield.removed_model_ids

    with pytest.raises(
        GameLifecycleError,
        match="destroyed unarrived reserve models must have exact removal state",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_phase16c_embarked_cargo_with_destroyed_model_in_reserves_round_trips() -> None:
    config = replace(
        _battle_formation_aggregate_config(),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:cargo-transport",
                points=100,
                source_id="phase16c-reserve-cargo-transport-points",
            ),
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:bodyguard-unit",
                points=100,
                source_id="phase16c-reserve-bodyguard-points",
            ),
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:leader-unit",
                points=100,
                source_id="phase16c-reserve-leader-points",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    state = lifecycle.state
    assert state is not None
    owner_army = state.army_definition_for_player("player-a")
    assert owner_army is not None
    bodyguard = owner_army.unit_by_id("army-alpha:bodyguard-unit")
    leader = owner_army.unit_by_id("army-alpha:leader-unit")
    destroyed_model = bodyguard.own_models[0]
    surviving_bodyguard_model_ids = tuple(
        model.model_instance_id for model in bodyguard.own_models[1:]
    )
    assert surviving_bodyguard_model_ids
    _replace_model_wounds_remaining(
        state=state,
        model_instance_id=destroyed_model.model_instance_id,
        wounds_remaining=0,
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    bodyguard_placement = UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=bodyguard.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=bodyguard.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(10.0 + 2.0 * index, 10.0),
            )
            for index, model in enumerate(bodyguard.own_models)
        ),
    )
    casualty_battlefield = (
        battlefield.with_added_unit_placement(bodyguard_placement)
        .with_removed_models((destroyed_model.model_instance_id,))
        .without_unit_placement(bodyguard.unit_instance_id)
    )
    state.replace_battlefield_state(casualty_battlefield)
    request = _decision_request(reserve_status)
    assert _option_ids(request) == (
        "complete_reserve_declarations",
        "declare_strategic_reserves:army-alpha:cargo-transport",
    )

    deployment_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-destroyed-model-reserve-cargo",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:cargo-transport",
        )
    )
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16c-destroyed-model-reserve-cargo-deployment",
    )
    final_battlefield = state.battlefield_state
    assert final_battlefield is not None
    reserve_state = state.reserve_state_for_unit("army-alpha:cargo-transport")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    assert reserve_state.embarked_unit_instance_ids == (
        "army-alpha:bodyguard-unit",
        "army-alpha:leader-unit",
    )
    placed_model_ids = set(final_battlefield.placed_model_ids())
    removed_model_ids = set(final_battlefield.removed_model_ids)
    assert set(surviving_bodyguard_model_ids).isdisjoint(placed_model_ids | removed_model_ids)
    assert destroyed_model.model_instance_id not in placed_model_ids
    assert destroyed_model.model_instance_id in removed_model_ids

    cargo_state = state.transport_cargo_state_for_transport("army-alpha:cargo-transport")
    assert cargo_state is not None
    current_owner_army = state.army_definition_for_player("player-a")
    assert current_owner_army is not None
    current_bodyguard = current_owner_army.unit_by_id(bodyguard.unit_instance_id)
    current_leader = current_owner_army.unit_by_id(leader.unit_instance_id)
    starting_cargo_model_count = len(current_bodyguard.own_models) + len(current_leader.own_models)
    living_cargo_model_count = sum(
        model.is_alive for unit in (current_bodyguard, current_leader) for model in unit.own_models
    )
    assert starting_cargo_model_count == 6
    assert living_cargo_model_count == 5
    assert cargo_state.capacity_profile.max_model_count == starting_cargo_model_count
    state.replace_transport_cargo_state(
        replace(
            cargo_state,
            capacity_profile=replace(
                cargo_state.capacity_profile,
                max_model_count=living_cargo_model_count,
                source_id="phase16c-damaged-cargo-capacity",
            ),
        )
    )

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)

    assert restored.state is not None
    restored_army = restored.state.army_definition_for_player("player-a")
    assert restored_army is not None
    restored_bodyguard = restored_army.unit_by_id(bodyguard.unit_instance_id)
    restored_destroyed_model = restored_bodyguard.own_models[0]
    assert restored_destroyed_model.model_instance_id == destroyed_model.model_instance_id
    assert restored_destroyed_model.wounds_remaining == 0
    assert (
        tuple(model.model_instance_id for model in restored_bodyguard.own_models[1:])
        == surviving_bodyguard_model_ids
    )
    restored_battlefield = restored.state.battlefield_state
    assert restored_battlefield is not None
    restored_placed_model_ids = set(restored_battlefield.placed_model_ids())
    restored_removed_model_ids = set(restored_battlefield.removed_model_ids)
    assert set(surviving_bodyguard_model_ids).isdisjoint(
        restored_placed_model_ids | restored_removed_model_ids
    )
    assert destroyed_model.model_instance_id not in restored_placed_model_ids
    assert destroyed_model.model_instance_id in restored_removed_model_ids

    cargo_drift_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    cargo_drift_state = cargo_drift_payload["state"]
    assert isinstance(cargo_drift_state, dict)
    reserve_payloads = cargo_drift_state["reserve_states"]
    assert isinstance(reserve_payloads, list)
    transport_reserve_payload = next(
        reserve_payload
        for reserve_payload in reserve_payloads
        if reserve_payload["unit_instance_id"] == "army-alpha:cargo-transport"
    )
    transport_reserve_payload["embarked_unit_instance_ids"] = ["army-alpha:bodyguard-unit"]

    with pytest.raises(
        GameLifecycleError,
        match="transport_cargo_states unarrived reserve route cargo drift",
    ):
        GameLifecycle.from_payload(cargo_drift_payload)

    missing_cargo_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    missing_cargo_state = missing_cargo_payload["state"]
    assert isinstance(missing_cargo_state, dict)
    cargo_payloads = missing_cargo_state["transport_cargo_states"]
    assert isinstance(cargo_payloads, list)
    cargo_payloads[:] = [
        cargo_payload
        for cargo_payload in cargo_payloads
        if cargo_payload["transport_unit_instance_id"] != "army-alpha:cargo-transport"
    ]
    assert all(
        cargo_payload["transport_unit_instance_id"] != "army-alpha:cargo-transport"
        for cargo_payload in cargo_payloads
    )
    missing_cargo_reserve_payloads = missing_cargo_state["reserve_states"]
    assert isinstance(missing_cargo_reserve_payloads, list)
    missing_cargo_reserve_payload = next(
        reserve_payload
        for reserve_payload in missing_cargo_reserve_payloads
        if reserve_payload["unit_instance_id"] == "army-alpha:cargo-transport"
    )
    assert missing_cargo_reserve_payload["embarked_unit_instance_ids"] == [
        "army-alpha:bodyguard-unit",
        "army-alpha:leader-unit",
    ]
    missing_cargo_game_state = GameState.from_payload(missing_cargo_state)
    missing_cargo_reserve_state = missing_cargo_game_state.reserve_state_for_unit(
        "army-alpha:cargo-transport"
    )
    assert missing_cargo_reserve_state is not None
    assert missing_cargo_reserve_state.is_unarrived
    assert missing_cargo_reserve_state.embarked_unit_instance_ids
    assert (
        missing_cargo_game_state.transport_cargo_state_for_transport("army-alpha:cargo-transport")
        is None
    )

    with pytest.raises(
        GameLifecycleError,
        match="transport_cargo_states unarrived reserve route cargo drift",
    ):
        GameLifecycle.from_payload(missing_cargo_payload)


def test_phase16c_aircraft_and_malformed_submission_errors_are_typed() -> None:
    aircraft_catalog = _catalog_with_datasheet_keywords(
        {
            "core-vehicle-monster": ("Aircraft", "Fly", "Vehicle"),
        }
    )
    aircraft_selection = _unit_selection(
        unit_selection_id="aircraft-unit",
        datasheet_id="core-vehicle-monster",
        model_profile_id="core-vehicle-monster",
        model_count=1,
    )
    missing_points_config = _config(
        catalog=aircraft_catalog,
        player_a_unit_selections=(aircraft_selection,),
    )
    missing_points_state = _state_at_declare_battle_formations(missing_points_config)
    with pytest.raises(GameLifecycleError, match="source-backed unit points"):
        apply_mandatory_aircraft_reserve_declarations(
            state=missing_points_state,
            config=missing_points_config,
            decisions=DecisionController(),
        )

    over_cap_config = _config(
        catalog=aircraft_catalog,
        player_a_unit_selections=(aircraft_selection,),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:aircraft-unit",
                points=1001,
                source_id="test-points:army-alpha:aircraft-unit",
            ),
        ),
    )
    over_cap_state = _state_at_declare_battle_formations(over_cap_config)
    with pytest.raises(GameLifecycleError, match="exceed the player's points limit"):
        apply_mandatory_aircraft_reserve_declarations(
            state=over_cap_state,
            config=over_cap_config,
            decisions=DecisionController(),
        )

    malformed_request = DecisionRequest(
        request_id="phase16c-malformed-request",
        decision_type=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        actor_id="player-a",
        payload={},
        options=(
            DecisionOption(
                option_id="complete_reserve_declarations",
                label="Complete Reserve Declarations",
                payload={},
            ),
        ),
    )
    malformed_status = invalid_reserve_declaration_status(
        state=missing_points_state,
        config=missing_points_config,
        request=malformed_request,
        result=DecisionResult.for_request(
            result_id="phase16c-malformed-result",
            request=malformed_request,
            selected_option_id="complete_reserve_declarations",
        ),
    )
    assert malformed_status is not None
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(malformed_status.payload, dict)
    assert malformed_status.payload["invalid_reason"] == "malformed_reserve_declaration"

    valid_config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="test-points:army-alpha:reserve-unit",
            ),
        ),
    )
    _valid_lifecycle, valid_status = _advance_to_reserve_request(valid_config)
    valid_request = _decision_request(valid_status)
    invalid_result_status = invalid_reserve_declaration_status(
        state=missing_points_state,
        config=valid_config,
        request=valid_request,
        result=DecisionResult(
            result_id="phase16c-invalid-option-result",
            request_id=valid_request.request_id,
            decision_type=valid_request.decision_type,
            actor_id=valid_request.actor_id,
            selected_option_id="missing-option",
            payload={},
        ),
    )
    assert invalid_result_status is not None
    assert invalid_result_status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(invalid_result_status.payload, dict)
    assert invalid_result_status.payload["invalid_reason"] == "invalid_reserve_declaration_result"


def _advance_to_reserve_request(config: GameConfig) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle, status = _advance_to_declaration_or_deployment(config)
    request = _decision_request(status)
    assert request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    return lifecycle, status


def _declared_strategic_reserve_lifecycle() -> tuple[GameLifecycle, str]:
    config = _config(
        player_a_unit_selections=(_unit_selection(unit_selection_id="reserve-unit"),),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="phase16c-physical-integrity-reserve-points",
            ),
        ),
    )
    lifecycle, reserve_status = _advance_to_reserve_request(config)
    request = _decision_request(reserve_status)
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase16c-physical-integrity-declaration",
            request=request,
            selected_option_id="declare_strategic_reserves:army-alpha:reserve-unit",
        )
    )
    state = lifecycle.state
    assert state is not None
    owner_army = state.army_definition_for_player("player-a")
    assert owner_army is not None
    reserve_unit = owner_army.unit_by_id("army-alpha:reserve-unit")
    return lifecycle, reserve_unit.own_models[0].model_instance_id


def _replace_model_wounds_remaining(
    *,
    state: GameState,
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


def _advance_to_deployment_or_later(config: GameConfig) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle, status = _advance_to_declaration_or_deployment(config)
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    ):
        request = status.decision_request
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase16c-complete-{request.request_id}",
                request=request,
                selected_option_id="complete_reserve_declarations",
            )
        )
    return lifecycle, status


def _advance_to_declaration_or_deployment(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = lifecycle.advance_until_decision_or_terminal()
    result_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        request = status.decision_request
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase16c-secondary-{result_index:06d}",
                request=request,
                selected_option_id="tactical",
            )
        )
        result_index += 1
    return lifecycle, status


def _state_at_declare_battle_formations(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-b", mode=SecondaryMissionMode.TACTICAL)
    )
    decisions = DecisionController()
    flow = SetupFlow()
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        flow.advance(state=state, decisions=decisions, config=config)
    return state


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    request = status.decision_request
    assert request is not None
    return request


def _option_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(option.option_id for option in request.options)


def _option_ids_from_options(options: tuple[DecisionOption, ...]) -> tuple[str, ...]:
    return tuple(option.option_id for option in options)


def _assert_opponent_formation_state_is_hidden(
    *,
    lifecycle: GameLifecycle,
    administrator: ViewerContext,
    model_instance_id: str,
) -> None:
    owner_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-a")
    opponent_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    admin_view = project_game_view(lifecycle=lifecycle, viewer=administrator)
    owner_battlefield = owner_view["battlefield_view"]
    opponent_battlefield = opponent_view["battlefield_view"]
    admin_battlefield = admin_view["battlefield_view"]
    assert owner_battlefield is not None
    assert opponent_battlefield is not None
    assert admin_battlefield is not None
    owner_model = owner_battlefield["authoritative"]["models_by_id"][model_instance_id]
    opponent_model = opponent_battlefield["authoritative"]["models_by_id"][model_instance_id]
    admin_model = admin_battlefield["authoritative"]["models_by_id"][model_instance_id]
    assert owner_model["state"] == "embarked"
    assert owner_model["state_context"]["transport_unit_instance_id"] == (
        "army-alpha:cargo-transport"
    )
    assert opponent_model["state"] == "undeployed"
    assert opponent_model["state_context"] == {
        "transport_unit_instance_id": None,
        "reserve_kind": None,
    }
    assert admin_model == owner_model


def _assert_opponent_premature_placement_is_hidden(
    *,
    lifecycle: GameLifecycle,
    administrator: ViewerContext,
    unit_instance_id: str,
) -> None:
    state = lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    model_instance_id = next(
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
        for model in unit.own_models
    )
    state.replace_battlefield_state(
        battlefield.with_added_unit_placement(
            UnitPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit_instance_id,
                model_placements=(
                    ModelPlacement(
                        army_id="army-alpha",
                        player_id="player-a",
                        unit_instance_id=unit_instance_id,
                        model_instance_id=model_instance_id,
                        pose=Pose.at(4.0, 5.0),
                    ),
                ),
            )
        )
    )
    owner_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-a")
    opponent_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    admin_view = project_game_view(lifecycle=lifecycle, viewer=administrator)
    owner_battlefield = owner_view["battlefield_view"]
    opponent_battlefield = opponent_view["battlefield_view"]
    admin_battlefield = admin_view["battlefield_view"]
    assert owner_battlefield is not None
    assert opponent_battlefield is not None
    assert admin_battlefield is not None
    assert owner_battlefield["authoritative"]["models_by_id"][model_instance_id]["state"] == (
        "placed"
    )
    assert (
        opponent_battlefield["authoritative"]["models_by_id"][model_instance_id]["state"]
        == "undeployed"
    )
    assert admin_battlefield["authoritative"]["models_by_id"][model_instance_id]["state"] == (
        "placed"
    )
    owner_raw = owner_view["battlefield_state"]
    opponent_raw = opponent_view["battlefield_state"]
    admin_raw = admin_view["battlefield_state"]
    assert isinstance(owner_raw, dict)
    assert isinstance(opponent_raw, dict)
    assert isinstance(admin_raw, dict)
    owner_placed_armies = owner_raw["placed_armies"]
    opponent_placed_armies = opponent_raw["placed_armies"]
    admin_placed_armies = admin_raw["placed_armies"]
    assert isinstance(owner_placed_armies, list)
    assert isinstance(opponent_placed_armies, list)
    assert isinstance(admin_placed_armies, list)
    assert len(owner_placed_armies) == 1
    assert opponent_placed_armies == []
    assert len(admin_placed_armies) == 1
    state.replace_battlefield_state(battlefield)


def _assert_current_setup_step(state: GameState, expected: SetupStep) -> None:
    assert state.current_setup_step is expected


def _battle_formation_aggregate_config() -> GameConfig:
    catalog = _catalog_with_datasheet_keywords(
        {"core-transport": ("Dedicated Transport", "Transport", "Vehicle")}
    )
    transport_capacity = DedicatedTransportCapacityProfile(
        transport_datasheet_id="core-transport",
        max_model_count=6,
        allowed_keywords=("Infantry",),
        excluded_keywords=(),
        source_id="phase16c-transport-capacity",
    )
    player_a_request = ArmyMusterRequest(
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
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="cargo-transport",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="empty-transport",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
            _unit_selection(unit_selection_id="reserve-unit"),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="cargo-transport",
                embarked_unit_selection_ids=("bodyguard-unit", "leader-unit"),
                capacity_profile=transport_capacity,
                source_id="phase16c-cargo-manifest",
            ),
            DedicatedTransportManifest(
                transport_unit_selection_id="empty-transport",
                embarked_unit_selection_ids=(),
                capacity_profile=transport_capacity,
                source_id="phase16c-empty-manifest",
            ),
        ),
    )
    return GameConfig(
        game_id="phase16c-aggregate-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            player_a_request,
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_unit_selection(unit_selection_id="intercessor-unit-2"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=400,
                source_id="phase16c-reserve-points",
            ),
        ),
    )


def _config(
    *,
    catalog: ArmyCatalog | None = None,
    player_a_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    reserve_unit_points: tuple[ReserveUnitPointValue, ...] = (),
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id="phase16c-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=resolved_catalog,
        army_muster_requests=_army_muster_requests(
            resolved_catalog,
            player_a_unit_selections=player_a_unit_selections,
            player_b_unit_selections=player_b_unit_selections,
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
        reserve_unit_points=reserve_unit_points,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16c-test")


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


def _army_muster_requests(
    catalog: ArmyCatalog,
    *,
    player_a_unit_selections: tuple[UnitMusterSelection, ...] | None,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None,
) -> tuple[ArmyMusterRequest, ...]:
    return (
        _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                (_unit_selection(unit_selection_id="intercessor-unit-1"),)
                if player_a_unit_selections is None
                else player_a_unit_selections
            ),
        ),
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                (_unit_selection(unit_selection_id="intercessor-unit-2"),)
                if player_b_unit_selections is None
                else player_b_unit_selections
            ),
        ),
    )


def _army_muster_request(
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=unit_selections,
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


def _catalog_with_datasheet_keywords(mapping: dict[str, tuple[str, ...]]) -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets = tuple(
        replace(
            datasheet,
            keywords=DatasheetKeywordSet(
                keywords=mapping.get(datasheet.datasheet_id, datasheet.keywords.keywords),
                faction_keywords=datasheet.keywords.faction_keywords,
            ),
        )
        for datasheet in base.datasheets
    )
    return replace(base, datasheets=datasheets)
