from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
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
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
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

    assert (
        restored_pending.decision_controller.queue.peek_next().to_payload() == request.to_payload()
    )

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
        defender_player_id="player-b",
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
        force_disposition_id="purge-the-foe",
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
