from __future__ import annotations

import json

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    RosterLegalityReport,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.cult_ambush import (
    GENESTEALER_CULTS_FACTION_ID,
    RESURGENCE_RESOURCE_KIND,
    SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
    SOURCE_RULE_ID,
    SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE,
    CultAmbushMarker,
    CultAmbushMarkerPayload,
    apply_cult_ambush_marker_ingress_selection,
    apply_cult_ambush_marker_placement_decision,
    apply_cult_ambush_placement,
    apply_cult_ambush_resurgence_decision,
    cult_ambush_marker_has_any_legal_position,
    cult_ambush_marker_ingress_request,
    cult_ambush_marker_position_violation,
    cult_ambush_resurgence_cost_for_unit,
    grant_initial_resurgence_points,
    invalid_cult_ambush_marker_placement_status,
    invalid_cult_ambush_placement_status,
    invalid_cult_ambush_resurgence_status,
    is_cult_ambush_placement_request,
    request_cult_ambush_resurgence,
    reserve_state_is_cult_ambush,
    resolve_cult_ambush_ingress_placement,
    resolve_cult_ambush_marker_removal_for_completed_moves,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    BattleSize,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.stratagems import (
    _rapid_ingress_unit_ids,
    _strategic_reserves_ingress_unit_ids,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext, TurnEndResultContext
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose

GSC_PLAYER_ID = "player-gsc"
ENEMY_PLAYER_ID = "player-enemy"
GSC_ARMY_ID = "army-gsc"
ENEMY_ARMY_ID = "army-enemy"
ACOLYTE_UNIT_ID = f"{GSC_ARMY_ID}:acolyte-hybrids"
NEOPHYTE_UNIT_ID = f"{GSC_ARMY_ID}:neophyte-hybrids"
ENEMY_UNIT_ID = f"{ENEMY_ARMY_ID}:enemy-unit"
ONE_SHOT_WARGEAR_ID = "demo-charge"
ONE_SHOT_PROFILE_ID = "demo-charge-profile"


def test_setup_grants_battle_size_resurgence_points_once() -> None:
    state = _setup_state(battle_size=BattleSize.STRIKE_FORCE)
    decisions = DecisionController()
    context = BattleFormationRequestContext(
        state=state,
        decisions=decisions,
        config=_config_for_context(state.game_id),
    )

    assert grant_initial_resurgence_points(context) is None
    assert grant_initial_resurgence_points(context) is None

    ledger = state.faction_resource_ledger_for_player(GSC_PLAYER_ID)
    assert ledger.total(RESURGENCE_RESOURCE_KIND) == 10
    assert (
        len(
            [
                transaction
                for transaction in ledger.transactions
                if transaction.resource_kind == RESURGENCE_RESOURCE_KIND
            ]
        )
        == 1
    )
    assert ledger.transactions[0].battle_round == 1
    assert json.loads(json.dumps(state.to_payload(), sort_keys=True)) == state.to_payload()


def test_cult_ambush_public_guards_fail_fast_for_wrong_context_types() -> None:
    with pytest.raises(GameLifecycleError, match="requires BattleFormationRequestContext"):
        grant_initial_resurgence_points(cast(BattleFormationRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires UnitDestroyedContext"):
        request_cult_ambush_resurgence(cast(UnitDestroyedContext, object()))
    with pytest.raises(GameLifecycleError, match="requires TurnEndRequestContext"):
        cult_ambush_marker_ingress_request(cast(TurnEndRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires TurnEndResultContext"):
        apply_cult_ambush_marker_ingress_selection(cast(TurnEndResultContext, object()))
    with pytest.raises(GameLifecycleError, match="requires DecisionRequest"):
        is_cult_ambush_placement_request(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="requires UnitInstance"):
        cult_ambush_resurgence_cost_for_unit(
            _setup_state(battle_size=BattleSize.STRIKE_FORCE),
            cast(UnitInstance, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires ReserveState"):
        reserve_state_is_cult_ambush(cast(ReserveState, object()))


def test_destroyed_unit_spends_resurgence_and_creates_cult_ambush_reserve() -> None:
    state, destroyed_unit, _enemy_unit = _battle_state(
        gsc_unit_id=NEOPHYTE_UNIT_ID,
        gsc_datasheet_id="neophyte-hybrids",
        gsc_unit_name="Neophyte Hybrids",
        gsc_model_count=10,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    first_model_id = destroyed_unit.own_models[0].model_instance_id
    state.record_one_shot_weapon_selected(
        model_instance_id=first_model_id,
        wargear_id=ONE_SHOT_WARGEAR_ID,
        weapon_profile_id=ONE_SHOT_PROFILE_ID,
        source_phase=BattlePhase.SHOOTING,
        selection_id="phase17g-gsc-used-one-shot",
    )
    decisions = DecisionController()
    request = _request_resurgence_for_destroyed_unit(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )

    assert request.decision_type == SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
    spend_option = _option_by_selection(request, "spend")
    result = DecisionResult.for_request(
        result_id="phase17g-gsc-spend-resurgence",
        request=request,
        selected_option_id=spend_option.option_id,
    )
    assert (
        invalid_cult_ambush_resurgence_status(state=state, request=request, result=result) is None
    )

    decisions.submit_result(result)
    apply_cult_ambush_resurgence_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )

    assert (
        state.faction_resource_total(
            player_id=GSC_PLAYER_ID,
            resource_kind=RESURGENCE_RESOURCE_KIND,
        )
        == 7
    )
    replacement = _unit_by_id(state, f"{destroyed_unit.unit_instance_id}:cult-ambush-001")
    assert replacement.unit_instance_id != destroyed_unit.unit_instance_id
    assert len(replacement.own_models) == 10
    assert all(model.wounds_remaining == model.starting_wounds for model in replacement.own_models)
    assert not state.one_shot_weapon_available(
        model_instance_id=first_model_id,
        wargear_id=ONE_SHOT_WARGEAR_ID,
        weapon_profile_id=ONE_SHOT_PROFILE_ID,
    )
    assert state.one_shot_weapon_available(
        model_instance_id=replacement.own_models[0].model_instance_id,
        wargear_id=ONE_SHOT_WARGEAR_ID,
        weapon_profile_id=ONE_SHOT_PROFILE_ID,
    )
    reserve_state = state.reserve_state_for_unit(replacement.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.DURING_BATTLE_ABILITY
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    assert SOURCE_RULE_ID in reserve_state.source_rule_ids
    marker_request = _next_request(decisions)
    assert marker_request.decision_type == SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE
    assert marker_request.actor_id == GSC_PLAYER_ID
    assert json.loads(json.dumps(marker_request.to_payload())) == marker_request.to_payload()


def test_destroyed_unit_declines_resurgence_without_mutation() -> None:
    state, destroyed_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    decisions = DecisionController()
    request = _request_resurgence_for_destroyed_unit(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )
    decline_result = DecisionResult.for_request(
        result_id="phase17g-gsc-decline-resurgence",
        request=request,
        selected_option_id=_option_by_selection(request, "decline").option_id,
    )

    assert (
        invalid_cult_ambush_resurgence_status(
            state=state,
            request=request,
            result=decline_result,
        )
        is None
    )
    decisions.submit_result(decline_result)
    apply_cult_ambush_resurgence_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=decline_result,
    )

    assert (
        state.faction_resource_total(
            player_id=GSC_PLAYER_ID,
            resource_kind=RESURGENCE_RESOURCE_KIND,
        )
        == 10
    )
    assert all(
        not unit.unit_instance_id.startswith(f"{destroyed_unit.unit_instance_id}:cult-ambush-")
        for army in state.army_definitions
        for unit in army.units
    )
    assert state.cult_ambush_markers == []
    assert _event_payloads(decisions, "genestealer_cults_cult_ambush_resurgence_declined")


def test_resurgence_hook_ignores_ineligible_or_duplicate_destroyed_units() -> None:
    state, destroyed_unit, enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    non_gsc_decisions = DecisionController()
    _run_resurgence_hook(
        state=state,
        decisions=non_gsc_decisions,
        destroyed_unit=enemy_unit,
        destroying_player_id=GSC_PLAYER_ID,
        destroyed_player_id=ENEMY_PLAYER_ID,
    )
    assert len(non_gsc_decisions.queue.pending_requests) == 0

    duplicate_decisions = DecisionController()
    event = duplicate_decisions.event_log.append(
        "model_destroyed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "destroying_player_id": ENEMY_PLAYER_ID,
                "target_unit_instance_id": destroyed_unit.unit_instance_id,
                "model_instance_id": destroyed_unit.own_models[-1].model_instance_id,
            }
        ),
    )
    context = UnitDestroyedContext(
        state=state,
        decisions=duplicate_decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=event.event_id,
        model_destroyed_payload=cast(dict[str, JsonValue], event.payload),
        destroying_player_id=ENEMY_PLAYER_ID,
        destroyed_unit_instance_id=destroyed_unit.unit_instance_id,
        destroyed_player_id=GSC_PLAYER_ID,
    )
    request_cult_ambush_resurgence(context)
    request_cult_ambush_resurgence(context)
    assert len(duplicate_decisions.queue.pending_requests) == 1
    duplicate_request = duplicate_decisions.queue.pending_requests[0]
    duplicate_decline = DecisionResult.for_request(
        result_id="phase17g-gsc-recorded-duplicate-decline",
        request=duplicate_request,
        selected_option_id=_option_by_selection(duplicate_request, "decline").option_id,
    )
    duplicate_decisions.submit_result(duplicate_decline)
    apply_cult_ambush_resurgence_decision(
        state=state,
        decisions=duplicate_decisions,
        request=duplicate_request,
        result=duplicate_decline,
    )
    request_cult_ambush_resurgence(context)
    assert list(duplicate_decisions.queue.pending_requests) == []

    no_ability_state, no_ability_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
        gsc_has_cult_ambush=False,
    )
    no_ability_decisions = DecisionController()
    _run_resurgence_hook(
        state=no_ability_state,
        decisions=no_ability_decisions,
        destroyed_unit=no_ability_unit,
    )
    assert len(no_ability_decisions.queue.pending_requests) == 0

    unsupported_state, unsupported_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="unsupported-cult-unit",
        gsc_unit_name="Unsupported Cult Unit",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    unsupported_decisions = DecisionController()
    _run_resurgence_hook(
        state=unsupported_state,
        decisions=unsupported_decisions,
        destroyed_unit=unsupported_unit,
    )
    assert len(unsupported_decisions.queue.pending_requests) == 0

    empty_resource_state, empty_resource_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=10,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    empty_resource_state.spend_faction_resource(
        player_id=GSC_PLAYER_ID,
        resource_kind=RESURGENCE_RESOURCE_KIND,
        amount=10,
        source_id="phase17g-gsc-empty-resurgence-ledger",
    )
    empty_resource_decisions = DecisionController()
    _run_resurgence_hook(
        state=empty_resource_state,
        decisions=empty_resource_decisions,
        destroyed_unit=empty_resource_unit,
    )
    assert len(empty_resource_decisions.queue.pending_requests) == 0


def test_resurgence_validation_rejects_result_and_state_drift() -> None:
    state, destroyed_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    decisions = DecisionController()
    request = _request_resurgence_for_destroyed_unit(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )
    spend_result = DecisionResult.for_request(
        result_id="phase17g-gsc-invalid-spend",
        request=request,
        selected_option_id=_option_by_selection(request, "spend").option_id,
    )
    wrong_option_result = replace(spend_result, selected_option_id="not-pending")

    wrong_option_status = invalid_cult_ambush_resurgence_status(
        state=state,
        request=request,
        result=wrong_option_result,
    )

    assert wrong_option_status is not None
    assert wrong_option_status.status_kind is LifecycleStatusKind.INVALID

    invalid_selection_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
        actor_id=GSC_PLAYER_ID,
        payload={},
        options=(
            DecisionOption(
                option_id="phase17g-gsc-invalid-selection",
                label="Invalid",
                payload={
                    "selection": "invalid",
                    "destroyed_unit_instance_id": destroyed_unit.unit_instance_id,
                },
            ),
        ),
    )
    invalid_selection_result = DecisionResult.for_request(
        result_id="phase17g-gsc-invalid-selection",
        request=invalid_selection_request,
        selected_option_id="phase17g-gsc-invalid-selection",
    )
    invalid_selection_status = invalid_cult_ambush_resurgence_status(
        state=state,
        request=invalid_selection_request,
        result=invalid_selection_result,
    )
    assert invalid_selection_status is not None
    assert invalid_selection_status.status_kind is LifecycleStatusKind.INVALID

    ability_drift_state, ability_drift_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    ability_drift_decisions = DecisionController()
    ability_drift_request = _request_resurgence_for_destroyed_unit(
        state=ability_drift_state,
        decisions=ability_drift_decisions,
        destroyed_unit=ability_drift_unit,
    )
    ability_drift_result = DecisionResult.for_request(
        result_id="phase17g-gsc-ability-drift",
        request=ability_drift_request,
        selected_option_id=_option_by_selection(ability_drift_request, "spend").option_id,
    )
    _replace_unit_in_state(
        ability_drift_state,
        replace(ability_drift_unit, datasheet_abilities=()),
    )
    ability_drift_status = invalid_cult_ambush_resurgence_status(
        state=ability_drift_state,
        request=ability_drift_request,
        result=ability_drift_result,
    )
    assert ability_drift_status is not None
    assert ability_drift_status.status_kind is LifecycleStatusKind.INVALID

    ineligible_state, ineligible_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    ineligible_decisions = DecisionController()
    ineligible_request = _request_resurgence_for_destroyed_unit(
        state=ineligible_state,
        decisions=ineligible_decisions,
        destroyed_unit=ineligible_unit,
    )
    ineligible_result = DecisionResult.for_request(
        result_id="phase17g-gsc-ineligible-drift",
        request=ineligible_request,
        selected_option_id=_option_by_selection(ineligible_request, "spend").option_id,
    )
    ineligible_state.starting_strength_records = [
        replace(record, starting_model_count=6)
        if record.unit_instance_id == ineligible_unit.unit_instance_id
        else record
        for record in ineligible_state.starting_strength_records
    ]
    ineligible_status = invalid_cult_ambush_resurgence_status(
        state=ineligible_state,
        request=ineligible_request,
        result=ineligible_result,
    )
    assert ineligible_status is not None
    assert ineligible_status.status_kind is LifecycleStatusKind.INVALID

    cost_drift_state, cost_drift_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    cost_drift_decisions = DecisionController()
    cost_drift_request = _request_resurgence_for_destroyed_unit(
        state=cost_drift_state,
        decisions=cost_drift_decisions,
        destroyed_unit=cost_drift_unit,
    )
    cost_drift_result = DecisionResult.for_request(
        result_id="phase17g-gsc-cost-drift",
        request=cost_drift_request,
        selected_option_id=_option_by_selection(cost_drift_request, "spend").option_id,
    )
    cost_drift_state.starting_strength_records = [
        replace(record, starting_model_count=10)
        if record.unit_instance_id == cost_drift_unit.unit_instance_id
        else record
        for record in cost_drift_state.starting_strength_records
    ]
    cost_drift_status = invalid_cult_ambush_resurgence_status(
        state=cost_drift_state,
        request=cost_drift_request,
        result=cost_drift_result,
    )
    assert cost_drift_status is not None
    assert cost_drift_status.status_kind is LifecycleStatusKind.INVALID

    state.spend_faction_resource(
        player_id=GSC_PLAYER_ID,
        resource_kind=RESURGENCE_RESOURCE_KIND,
        amount=10,
        source_id="phase17g-gsc-spend-before-validation",
    )
    insufficient_status = invalid_cult_ambush_resurgence_status(
        state=state,
        request=request,
        result=spend_result,
    )
    assert insufficient_status is not None
    assert insufficient_status.status_kind is LifecycleStatusKind.INVALID


def test_spending_resurgence_without_legal_marker_records_no_marker_event() -> None:
    state, destroyed_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
        enemy_x=0.5,
        enemy_y=0.5,
    )
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            battlefield_state,
            battlefield_width_inches=1.0,
            battlefield_depth_inches=1.0,
        )
    )
    decisions = DecisionController()
    request = _request_resurgence_for_destroyed_unit(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )
    spend_result = DecisionResult.for_request(
        result_id="phase17g-gsc-spend-no-marker",
        request=request,
        selected_option_id=_option_by_selection(request, "spend").option_id,
    )

    decisions.submit_result(spend_result)
    apply_cult_ambush_resurgence_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=spend_result,
    )

    assert len(decisions.queue.pending_requests) == 0
    assert _event_payloads(decisions, "genestealer_cults_cult_ambush_marker_not_placed")


def test_marker_placement_validates_enemy_distance_and_serializes() -> None:
    state, decisions, marker_request, _replacement = _state_waiting_for_marker_placement(
        enemy_x=30.0,
        enemy_y=30.0,
    )
    invalid_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-invalid",
        x_inches=30.0,
        y_inches=30.0,
    )

    invalid_status = invalid_cult_ambush_marker_placement_status(
        state=state,
        request=marker_request,
        result=invalid_result,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert state.cult_ambush_markers == []

    valid_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-valid",
        x_inches=5.0,
        y_inches=5.0,
    )
    assert (
        invalid_cult_ambush_marker_placement_status(
            state=state,
            request=marker_request,
            result=valid_result,
        )
        is None
    )
    decisions.submit_result(valid_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=valid_result,
    )

    assert len(state.cult_ambush_markers) == 1
    marker = state.cult_ambush_markers[0]
    assert marker.x_inches == 5.0
    assert marker.y_inches == 5.0
    payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    restored = GameState.from_payload(payload)
    assert restored.cult_ambush_markers == state.cult_ambush_markers


def test_cult_ambush_marker_payload_rejects_invalid_fields() -> None:
    base_payload = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=5.0,
        y_inches=5.0,
    ).to_payload()
    invalid_payloads = (
        (dict(base_payload, marker_id=""), "must not be empty"),
        (dict(base_payload, created_battle_round=0), "must be positive"),
        (dict(base_payload, created_phase=1), "battle phase must be a string"),
        (dict(base_payload, created_phase="invalid-phase"), "Unsupported Cult Ambush"),
        (dict(base_payload, x_inches=float("nan")), "must be finite"),
        (dict(base_payload, marker_diameter_inches=0.0), "must be positive"),
        (dict(base_payload, ingress_window_closed="false"), "must be a bool"),
    )

    for payload, match in invalid_payloads:
        with pytest.raises(GameLifecycleError, match=match):
            CultAmbushMarker.from_payload(cast(CultAmbushMarkerPayload, payload))


def test_marker_position_requires_battlefield_state() -> None:
    state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    state.battlefield_state = None

    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        cult_ambush_marker_position_violation(
            state,
            player_id=GSC_PLAYER_ID,
            x_inches=8.0,
            y_inches=8.0,
        )
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        cult_ambush_marker_has_any_legal_position(state, player_id=GSC_PLAYER_ID)


def test_no_marker_submission_records_when_no_legal_position_exists() -> None:
    state, decisions, marker_request, _replacement = _state_waiting_for_marker_placement(
        enemy_x=0.5,
        enemy_y=0.5,
    )
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            battlefield_state,
            battlefield_width_inches=1.0,
            battlefield_depth_inches=1.0,
        )
    )
    no_marker_result = _no_marker_result(
        request=marker_request,
        result_id="phase17g-gsc-no-marker",
    )

    assert (
        invalid_cult_ambush_marker_placement_status(
            state=state,
            request=marker_request,
            result=no_marker_result,
        )
        is None
    )
    decisions.submit_result(no_marker_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=no_marker_result,
    )

    assert state.cult_ambush_markers == []
    payloads = _event_payloads(decisions, "genestealer_cults_cult_ambush_marker_not_placed")
    assert payloads[-1]["reason"] == "no_legal_marker_position"


def test_marker_placement_rejects_stale_and_malformed_submissions() -> None:
    state, _decisions, marker_request, _replacement = _state_waiting_for_marker_placement(
        enemy_x=30.0,
        enemy_y=30.0,
    )
    valid_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-valid-base",
        x_inches=5.0,
        y_inches=5.0,
    )
    no_marker_status = invalid_cult_ambush_marker_placement_status(
        state=state,
        request=marker_request,
        result=_no_marker_result(
            request=marker_request,
            result_id="phase17g-gsc-no-marker-while-legal",
        ),
    )
    assert no_marker_status is not None
    assert no_marker_status.status_kind is LifecycleStatusKind.INVALID

    drifted_payload = dict(cast(dict[str, JsonValue], valid_result.payload))
    drifted_payload["marker_id"] = "different-marker"
    drifted_marker_status = invalid_cult_ambush_marker_placement_status(
        state=state,
        request=marker_request,
        result=replace(
            valid_result,
            result_id="phase17g-gsc-marker-drift",
            payload=validate_json_value(drifted_payload),
        ),
    )
    assert drifted_marker_status is not None
    assert drifted_marker_status.status_kind is LifecycleStatusKind.INVALID

    malformed_payload = dict(cast(dict[str, JsonValue], valid_result.payload))
    malformed_payload["submission_kind"] = "wrong_kind"
    malformed_status = invalid_cult_ambush_marker_placement_status(
        state=state,
        request=marker_request,
        result=replace(
            valid_result,
            result_id="phase17g-gsc-marker-wrong-kind",
            payload=validate_json_value(malformed_payload),
        ),
    )
    assert malformed_status is not None
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID

    request_payload_drift = dict(cast(dict[str, JsonValue], valid_result.payload))
    request_payload_drift["request_id"] = "different-request"
    player_drift = dict(cast(dict[str, JsonValue], valid_result.payload))
    player_drift["player_id"] = ENEMY_PLAYER_ID
    for drifted_result in (
        replace(valid_result, request_id="different-request"),
        replace(valid_result, decision_type="different_decision"),
        replace(valid_result, actor_id=ENEMY_PLAYER_ID),
        replace(valid_result, selected_option_id="different-option"),
        replace(
            valid_result,
            result_id="phase17g-gsc-marker-request-payload-drift",
            payload=validate_json_value(request_payload_drift),
        ),
        replace(
            valid_result,
            result_id="phase17g-gsc-marker-player-drift",
            payload=validate_json_value(player_drift),
        ),
    ):
        drift_status = invalid_cult_ambush_marker_placement_status(
            state=state,
            request=marker_request,
            result=drifted_result,
        )
        assert drift_status is not None
        assert drift_status.status_kind is LifecycleStatusKind.INVALID


def test_cult_ambush_reserve_cannot_rapid_ingress_but_remains_strategic_reserves() -> None:
    state, _decisions, _marker_request, replacement = _state_waiting_for_marker_placement(
        enemy_x=40.0,
        enemy_y=40.0,
    )

    assert replacement.unit_instance_id not in _rapid_ingress_unit_ids(
        state=state,
        player_id=GSC_PLAYER_ID,
    )
    assert replacement.unit_instance_id in _strategic_reserves_ingress_unit_ids(
        state=state,
        player_id=GSC_PLAYER_ID,
    )


def test_enemy_non_aircraft_move_removes_marker_but_aircraft_move_does_not() -> None:
    state, _gsc_unit, enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
        enemy_x=10.0,
        enemy_y=10.0,
    )
    marker = _marker(replacement_unit_instance_id=ACOLYTE_UNIT_ID, x_inches=10.0, y_inches=10.0)
    state.record_cult_ambush_marker(marker)
    decisions = DecisionController()
    trigger_event = decisions.event_log.append(
        "movement_activation_completed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": enemy_unit.unit_instance_id,
            }
        ),
    )

    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.MOVEMENT,
    )

    assert state.cult_ambush_markers == []
    removed_payloads = _event_payloads(decisions, "genestealer_cults_cult_ambush_marker_removed")
    assert removed_payloads[0]["trigger_event_id"] == trigger_event.event_id
    state.record_cult_ambush_marker(marker)

    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.MOVEMENT,
    )

    assert state.cult_ambush_markers == [marker]

    aircraft_state, _gsc_unit, aircraft_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
        enemy_x=10.0,
        enemy_y=10.0,
        enemy_aircraft=True,
    )
    aircraft_marker = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=10.0,
        y_inches=10.0,
    )
    aircraft_state.record_cult_ambush_marker(aircraft_marker)
    aircraft_decisions = DecisionController()
    aircraft_decisions.event_log.append(
        "movement_activation_completed",
        validate_json_value(
            {
                "game_id": aircraft_state.game_id,
                "battle_round": aircraft_state.battle_round,
                "active_player_id": aircraft_state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": aircraft_unit.unit_instance_id,
            }
        ),
    )

    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=aircraft_state,
        decisions=aircraft_decisions,
        completed_phase=BattlePhase.MOVEMENT,
    )

    assert aircraft_state.cult_ambush_markers == [aircraft_marker]


def test_marker_removal_rejects_non_object_move_event_payload() -> None:
    state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
    )
    state.record_cult_ambush_marker(
        _marker(
            replacement_unit_instance_id=ACOLYTE_UNIT_ID,
            x_inches=10.0,
            y_inches=10.0,
        )
    )
    decisions = DecisionController()
    decisions.event_log.append(
        "movement_activation_completed",
        validate_json_value(["not-object"]),
    )

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        resolve_cult_ambush_marker_removal_for_completed_moves(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )


def test_marker_removal_ignores_unmatched_events_and_missing_context() -> None:
    empty_state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
    )
    empty_decisions = DecisionController()
    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=empty_state,
        decisions=empty_decisions,
        completed_phase=BattlePhase.MOVEMENT,
    )

    no_battlefield_state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
    )
    no_battlefield_marker = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=1.0,
        y_inches=1.0,
    )
    no_battlefield_state.record_cult_ambush_marker(no_battlefield_marker)
    no_battlefield_state.battlefield_state = None
    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=no_battlefield_state,
        decisions=DecisionController(),
        completed_phase=BattlePhase.MOVEMENT,
    )
    assert no_battlefield_state.cult_ambush_markers == [no_battlefield_marker]

    state, _gsc_unit, enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
        enemy_x=40.0,
        enemy_y=40.0,
    )
    marker = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=1.0,
        y_inches=1.0,
    )
    state.record_cult_ambush_marker(marker)
    decisions = DecisionController()
    event_payloads = (
        ("unrelated_event", {"game_id": state.game_id}),
        (
            "movement_activation_completed",
            {
                "game_id": "other-game",
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": enemy_unit.unit_instance_id,
            },
        ),
        (
            "movement_activation_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round + 1,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": enemy_unit.unit_instance_id,
            },
        ),
        (
            "movement_activation_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": GSC_PLAYER_ID,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": enemy_unit.unit_instance_id,
            },
        ),
        (
            "movement_activation_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": enemy_unit.unit_instance_id,
            },
        ),
        (
            "movement_activation_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
            },
        ),
        (
            "movement_activation_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": ACOLYTE_UNIT_ID,
            },
        ),
        (
            "charge_move_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "target_unit_instance_id": enemy_unit.unit_instance_id,
            },
        ),
    )
    for event_type, payload in event_payloads:
        decisions.event_log.append(event_type, validate_json_value(payload))

    resolve_cult_ambush_marker_removal_for_completed_moves(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.MOVEMENT,
    )

    assert state.cult_ambush_markers == [marker]
    assert not _event_payloads(decisions, "genestealer_cults_cult_ambush_marker_removed")


def test_marker_ingress_decline_closes_marker_window_without_placement_request() -> None:
    state, decisions, marker_request, _replacement = _state_waiting_for_marker_placement(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        enemy_x=40.0,
        enemy_y=40.0,
    )
    marker_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-for-decline",
        x_inches=8.0,
        y_inches=8.0,
    )
    decisions.submit_result(marker_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=marker_result,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    ingress_request = cult_ambush_marker_ingress_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )
    )
    assert ingress_request is not None
    decline_result = DecisionResult.for_request(
        result_id="phase17g-gsc-decline-marker-ingress",
        request=ingress_request,
        selected_option_id=_option_by_selection(ingress_request, "decline").option_id,
    )

    assert apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=ingress_request,
            result=decline_result,
        )
    )

    assert len(state.cult_ambush_markers) == 1
    assert state.cult_ambush_markers[0].ingress_window_closed
    assert not _event_payloads(decisions, "placement_proposal_requested")


def test_marker_ingress_request_ignores_wrong_phase_and_missing_reserve() -> None:
    wrong_phase_state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    wrong_phase_state.record_cult_ambush_marker(
        _marker(
            replacement_unit_instance_id=ACOLYTE_UNIT_ID,
            x_inches=8.0,
            y_inches=8.0,
        )
    )
    wrong_phase_decisions = DecisionController()
    assert (
        cult_ambush_marker_ingress_request(
            TurnEndRequestContext(
                state=wrong_phase_state,
                decisions=wrong_phase_decisions,
                completed_phase=BattlePhase.SHOOTING,
            )
        )
        is None
    )

    state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
    )
    marker = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=8.0,
        y_inches=8.0,
    )
    state.record_cult_ambush_marker(marker)
    decisions = DecisionController()

    assert (
        cult_ambush_marker_ingress_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.MOVEMENT,
            )
        )
        is None
    )
    state.remove_cult_ambush_marker(marker.marker_id)
    assert (
        cult_ambush_marker_ingress_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.MOVEMENT,
            )
        )
        is None
    )


def test_marker_ingress_selection_routing_and_invalid_selection_fail_fast() -> None:
    state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.MOVEMENT,
        active_player_id=ENEMY_PLAYER_ID,
    )
    marker = _marker(
        replacement_unit_instance_id=ACOLYTE_UNIT_ID,
        x_inches=8.0,
        y_inches=8.0,
    )
    state.record_cult_ambush_marker(marker)
    decisions = DecisionController()
    base_request = DecisionRequest(
        request_id="phase17g-gsc-ingress-routing",
        decision_type="select_faction_rule_turn_end_option",
        actor_id=GSC_PLAYER_ID,
        payload={
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": f"{SOURCE_RULE_ID}:other_hook",
        },
        options=(
            DecisionOption(
                option_id="phase17g-gsc-ingress-routing-option",
                label="Ingress Routing",
                payload={},
            ),
        ),
    )
    decline_result = DecisionResult(
        result_id="phase17g-gsc-ingress-routing-result",
        request_id=base_request.request_id,
        decision_type=base_request.decision_type,
        actor_id=base_request.actor_id,
        selected_option_id="phase17g-gsc-ingress-routing-option",
        payload=validate_json_value(
            {
                "marker_id": marker.marker_id,
                "selection": "decline",
            }
        ),
    )

    assert not apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=replace(
                base_request,
                payload={"source_rule_id": "other", "hook_id": "other"},
            ),
            result=decline_result,
        )
    )
    assert not apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=base_request,
            result=decline_result,
        )
    )

    invalid_selection_result = replace(
        decline_result,
        result_id="phase17g-gsc-ingress-invalid-selection",
        payload=validate_json_value(
            {
                "marker_id": marker.marker_id,
                "selection": "invalid",
            }
        ),
    )
    with pytest.raises(GameLifecycleError, match="was not prevalidated"):
        apply_cult_ambush_marker_ingress_selection(
            TurnEndResultContext(
                state=state,
                decisions=decisions,
                request=replace(
                    base_request,
                    payload={
                        "source_rule_id": SOURCE_RULE_ID,
                        "hook_id": f"{SOURCE_RULE_ID}:marker_ingress",
                    },
                ),
                result=invalid_selection_result,
            )
        )


def test_marker_ingress_sets_up_cult_ambush_unit_in_first_round() -> None:
    state, decisions, marker_request, replacement = _state_waiting_for_marker_placement(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        enemy_x=40.0,
        enemy_y=40.0,
    )
    marker_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-for-ingress",
        x_inches=8.0,
        y_inches=8.0,
    )
    decisions.submit_result(marker_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=marker_result,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)

    ingress_request = cult_ambush_marker_ingress_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )
    )

    assert ingress_request is not None
    assert ingress_request.actor_id == GSC_PLAYER_ID
    ingress_option = _option_by_selection(ingress_request, "ingress")
    ingress_result = DecisionResult.for_request(
        result_id="phase17g-gsc-select-marker-ingress",
        request=ingress_request,
        selected_option_id=ingress_option.option_id,
    )
    assert apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=ingress_request,
            result=ingress_result,
        )
    )
    placement_request = _next_request(decisions)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    assert proposal_request.proposal_kind is ProposalKind.CULT_AMBUSH
    assert proposal_request.battle_round == 1
    attempted_placement = _unit_placement_for_marker_unit(
        unit=replacement,
        x_inches=8.0,
        y_inches=8.0,
    )
    placement_result = DecisionResult(
        result_id="phase17g-gsc-submit-marker-ingress-placement",
        request_id=placement_request.request_id,
        decision_type=placement_request.decision_type,
        actor_id=placement_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                unit_instance_id=replacement.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
                attempted_placement=attempted_placement,
            ).to_payload()
        ),
    )

    assert (
        invalid_cult_ambush_placement_status(
            state=state,
            request=placement_request,
            result=placement_result,
        )
        is None
    )
    decisions.submit_result(placement_result)
    status = apply_cult_ambush_placement(
        state=state,
        decisions=decisions,
        request=placement_request,
        result=placement_result,
    )

    assert status is None
    assert state.cult_ambush_markers == []
    arrived_state = state.reserve_state_for_unit(replacement.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert arrived_state.arrived_battle_round == 1
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(replacement.unit_instance_id)


def test_invalid_marker_ingress_placement_records_retry_without_arrival() -> None:
    state, decisions, marker_request, replacement = _state_waiting_for_marker_placement(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        enemy_x=40.0,
        enemy_y=40.0,
    )
    marker_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-for-invalid-placement",
        x_inches=8.0,
        y_inches=8.0,
    )
    decisions.submit_result(marker_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=marker_result,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    ingress_request = cult_ambush_marker_ingress_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )
    )
    assert ingress_request is not None
    ingress_result = DecisionResult.for_request(
        result_id="phase17g-gsc-select-invalid-placement-ingress",
        request=ingress_request,
        selected_option_id=_option_by_selection(ingress_request, "ingress").option_id,
    )
    assert apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=ingress_request,
            result=ingress_result,
        )
    )
    placement_request = _next_request(decisions)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    invalid_placement_result = DecisionResult(
        result_id="phase17g-gsc-invalid-marker-ingress-placement",
        request_id=placement_request.request_id,
        decision_type=placement_request.decision_type,
        actor_id=placement_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                unit_instance_id=replacement.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
                attempted_placement=_unit_placement_for_marker_unit(
                    unit=replacement,
                    x_inches=30.0,
                    y_inches=30.0,
                ),
            ).to_payload()
        ),
    )

    assert (
        invalid_cult_ambush_placement_status(
            state=state,
            request=placement_request,
            result=invalid_placement_result,
        )
        is None
    )
    decisions.submit_result(invalid_placement_result)
    status = apply_cult_ambush_placement(
        state=state,
        decisions=decisions,
        request=placement_request,
        result=invalid_placement_result,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.cult_ambush_markers
    reserve_state = state.reserve_state_for_unit(replacement.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    retry_request = _next_request(decisions)
    retry_proposal = MovementProposalRequest.from_decision_request_payload(retry_request.payload)
    assert retry_proposal.proposal_kind is ProposalKind.CULT_AMBUSH


def test_cult_ambush_placement_request_routing_and_submission_drift() -> None:
    state, _decisions, placement_request, replacement = _state_waiting_for_ingress_placement()

    assert is_cult_ambush_placement_request(placement_request)
    assert not is_cult_ambush_placement_request(
        DecisionRequest(
            request_id="phase17g-gsc-not-placement",
            decision_type="not_placement",
            actor_id=GSC_PLAYER_ID,
            payload={},
            options=(
                DecisionOption(
                    option_id="phase17g-gsc-not-placement-option",
                    label="Not Placement",
                    payload={},
                ),
            ),
        )
    )

    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    attempted_placement = _unit_placement_for_marker_unit(
        unit=replacement,
        x_inches=8.0,
        y_inches=8.0,
    )
    base_payload = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=replacement.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
        attempted_placement=attempted_placement,
    ).to_payload()

    request_id_drift = dict(base_payload)
    request_id_drift["proposal_request_id"] = "phase17g-gsc-stale-proposal"
    kind_drift = dict(base_payload)
    kind_drift["proposal_kind"] = ProposalKind.STRATEGIC_RESERVES.value
    placement_kind_drift = dict(base_payload)
    placement_kind_drift["placement_kind"] = BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    wrong_unit_placement = UnitPlacement(
        army_id=GSC_ARMY_ID,
        player_id=GSC_PLAYER_ID,
        unit_instance_id=ACOLYTE_UNIT_ID,
        model_placements=tuple(
            replace(model_placement, unit_instance_id=ACOLYTE_UNIT_ID)
            for model_placement in attempted_placement.model_placements
        ),
    )
    unit_drift = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=ACOLYTE_UNIT_ID,
        placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
        attempted_placement=wrong_unit_placement,
    ).to_payload()

    for index, payload in enumerate(
        (request_id_drift, kind_drift, unit_drift, placement_kind_drift),
        start=1,
    ):
        result = DecisionResult(
            result_id=f"phase17g-gsc-placement-drift-{index}",
            request_id=placement_request.request_id,
            decision_type=placement_request.decision_type,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(payload),
        )
        status = invalid_cult_ambush_placement_status(
            state=state,
            request=placement_request,
            result=result,
        )

        assert status is not None
        assert status.status_kind is LifecycleStatusKind.INVALID


def test_marker_position_rejects_unknown_enemy_model_reference() -> None:
    state, _gsc_unit, _enemy_unit = _battle_state(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
    )
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    enemy_army = battlefield_state.placed_armies[0]
    enemy_placement = enemy_army.unit_placements[0]
    unknown_enemy_models = (
        replace(
            enemy_placement.model_placements[0],
            model_instance_id=f"{ENEMY_UNIT_ID}:unknown-model",
        ),
        *enemy_placement.model_placements[1:],
    )
    state.replace_battlefield_state(
        replace(
            battlefield_state,
            placed_armies=(
                replace(
                    enemy_army,
                    unit_placements=(
                        replace(
                            enemy_placement,
                            model_placements=unknown_enemy_models,
                        ),
                    ),
                ),
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="unknown model"):
        cult_ambush_marker_position_violation(
            state,
            player_id=GSC_PLAYER_ID,
            x_inches=8.0,
            y_inches=8.0,
        )


def test_cult_ambush_ingress_resolution_reports_state_drift_violations() -> None:
    missing_reserve_state, _decisions, placement_request, replacement = (
        _state_waiting_for_ingress_placement()
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    submitted = _cult_ambush_placement_payload(
        proposal_request=proposal_request,
        unit=replacement,
    )
    missing_reserve_state.reserve_states = [
        reserve_state
        for reserve_state in missing_reserve_state.reserve_states
        if reserve_state.unit_instance_id != replacement.unit_instance_id
    ]

    missing_reserve = resolve_cult_ambush_ingress_placement(
        state=missing_reserve_state,
        proposal_request=proposal_request,
        submitted=submitted,
    )

    assert "reserve_state_missing" in _violation_codes(missing_reserve.validation_result)

    arrived_state, _decisions, placement_request, replacement = (
        _state_waiting_for_ingress_placement()
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    submitted = _cult_ambush_placement_payload(
        proposal_request=proposal_request,
        unit=replacement,
    )
    reserve_state = arrived_state.reserve_state_for_unit(replacement.unit_instance_id)
    assert reserve_state is not None
    arrived_state.replace_reserve_state(
        reserve_state.mark_arrived(
            battle_round=arrived_state.battle_round,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )

    arrived = resolve_cult_ambush_ingress_placement(
        state=arrived_state,
        proposal_request=proposal_request,
        submitted=submitted,
    )

    assert "reserve_state_not_unarrived" in _violation_codes(arrived.validation_result)

    wrong_source_state, _decisions, placement_request, replacement = (
        _state_waiting_for_ingress_placement()
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    submitted = _cult_ambush_placement_payload(
        proposal_request=proposal_request,
        unit=replacement,
    )
    reserve_state = wrong_source_state.reserve_state_for_unit(replacement.unit_instance_id)
    assert reserve_state is not None
    wrong_source_state.replace_reserve_state(replace(reserve_state, source_rule_ids=("other",)))

    wrong_source = resolve_cult_ambush_ingress_placement(
        state=wrong_source_state,
        proposal_request=proposal_request,
        submitted=submitted,
    )

    assert "reserve_state_not_cult_ambush" in _violation_codes(wrong_source.validation_result)

    missing_marker_state, _decisions, placement_request, replacement = (
        _state_waiting_for_ingress_placement()
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    submitted = _cult_ambush_placement_payload(
        proposal_request=proposal_request,
        unit=replacement,
    )
    missing_marker_state.remove_cult_ambush_marker(
        missing_marker_state.cult_ambush_markers[0].marker_id
    )

    missing_marker = resolve_cult_ambush_ingress_placement(
        state=missing_marker_state,
        proposal_request=proposal_request,
        submitted=submitted,
    )

    assert "marker_not_active" in _violation_codes(missing_marker.validation_result)

    player_drift_state, _decisions, placement_request, replacement = (
        _state_waiting_for_ingress_placement()
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    player_drift_placement = _unit_placement_for_marker_unit(
        unit=replacement,
        x_inches=8.0,
        y_inches=8.0,
    )
    player_drift_placement = UnitPlacement(
        army_id=GSC_ARMY_ID,
        player_id=ENEMY_PLAYER_ID,
        unit_instance_id=player_drift_placement.unit_instance_id,
        model_placements=tuple(
            replace(model_placement, player_id=ENEMY_PLAYER_ID)
            for model_placement in player_drift_placement.model_placements
        ),
    )
    player_drift = resolve_cult_ambush_ingress_placement(
        state=player_drift_state,
        proposal_request=proposal_request,
        submitted=PlacementProposalPayload(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=replacement.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
            attempted_placement=player_drift_placement,
        ),
    )

    assert "player_id_drift" in _violation_codes(player_drift.validation_result)


def _setup_state(*, battle_size: BattleSize) -> GameState:
    descriptor = _ruleset_descriptor()
    setup_sequence = tuple(descriptor.setup_sequence.steps)
    state = GameState(
        game_id="phase17g-genestealer-cults-setup",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.SETUP,
        setup_sequence=setup_sequence,
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        player_ids=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        turn_order=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        tactical_secondary_draw_count=2,
        setup_step_index=setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS),
    )
    state.record_army_definition(
        _army(
            army_id=GSC_ARMY_ID,
            player_id=GSC_PLAYER_ID,
            faction_id=GENESTEALER_CULTS_FACTION_ID,
            battle_size=battle_size,
            units=(
                _unit(
                    unit_instance_id=ACOLYTE_UNIT_ID,
                    datasheet_id="acolyte-hybrids-with-autopistols",
                    name="Acolyte Hybrids with Autopistols",
                    model_count=5,
                    has_cult_ambush=True,
                ),
            ),
        )
    )
    state.record_army_definition(
        _army(
            army_id=ENEMY_ARMY_ID,
            player_id=ENEMY_PLAYER_ID,
            faction_id="adeptus-astartes",
            battle_size=battle_size,
            units=(
                _unit(
                    unit_instance_id=ENEMY_UNIT_ID,
                    datasheet_id="enemy-intercessors",
                    name="Enemy Intercessors",
                    model_count=1,
                    has_cult_ambush=False,
                ),
            ),
        )
    )
    return state


def _battle_state(
    *,
    gsc_unit_id: str,
    gsc_datasheet_id: str,
    gsc_unit_name: str,
    gsc_model_count: int,
    phase: BattlePhase,
    active_player_id: str,
    enemy_x: float = 40.0,
    enemy_y: float = 40.0,
    enemy_aircraft: bool = False,
    gsc_has_cult_ambush: bool = True,
) -> tuple[GameState, UnitInstance, UnitInstance]:
    descriptor = _ruleset_descriptor()
    battle_phase_sequence = tuple(descriptor.battle_phase_sequence.phases)
    gsc_unit = _unit(
        unit_instance_id=gsc_unit_id,
        datasheet_id=gsc_datasheet_id,
        name=gsc_unit_name,
        model_count=gsc_model_count,
        has_cult_ambush=gsc_has_cult_ambush,
    )
    enemy_unit = _unit(
        unit_instance_id=ENEMY_UNIT_ID,
        datasheet_id="enemy-aircraft" if enemy_aircraft else "enemy-intercessors",
        name="Enemy Aircraft" if enemy_aircraft else "Enemy Intercessors",
        model_count=1,
        has_cult_ambush=False,
        keywords=("AIRCRAFT",) if enemy_aircraft else ("INFANTRY",),
    )
    gsc_army = _army(
        army_id=GSC_ARMY_ID,
        player_id=GSC_PLAYER_ID,
        faction_id=GENESTEALER_CULTS_FACTION_ID,
        battle_size=BattleSize.STRIKE_FORCE,
        units=(gsc_unit,),
    )
    enemy_army = _army(
        army_id=ENEMY_ARMY_ID,
        player_id=ENEMY_PLAYER_ID,
        faction_id="adeptus-astartes",
        battle_size=BattleSize.STRIKE_FORCE,
        units=(enemy_unit,),
    )
    state = GameState(
        game_id="phase17g-genestealer-cults-battle",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=battle_phase_sequence,
        player_ids=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        turn_order=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phase_sequence.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
    )
    state.record_army_definition(gsc_army)
    state.record_army_definition(enemy_army)
    state.battlefield_state = BattlefieldRuntimeState(
        battlefield_id="phase17g-genestealer-cults-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=ENEMY_ARMY_ID,
                player_id=ENEMY_PLAYER_ID,
                unit_placements=(
                    _unit_placement(
                        army_id=ENEMY_ARMY_ID,
                        player_id=ENEMY_PLAYER_ID,
                        unit=enemy_unit,
                        x_inches=enemy_x,
                        y_inches=enemy_y,
                    ),
                ),
            ),
        ),
    )
    state.gain_faction_resource(
        player_id=GSC_PLAYER_ID,
        resource_kind=RESURGENCE_RESOURCE_KIND,
        amount=10,
        source_id="phase17g-gsc-test-resurgence-grant",
    )
    return state, gsc_unit, enemy_unit


def _state_waiting_for_marker_placement(
    *,
    gsc_unit_id: str = NEOPHYTE_UNIT_ID,
    gsc_datasheet_id: str = "neophyte-hybrids",
    gsc_unit_name: str = "Neophyte Hybrids",
    gsc_model_count: int = 10,
    enemy_x: float,
    enemy_y: float,
) -> tuple[GameState, DecisionController, DecisionRequest, UnitInstance]:
    state, destroyed_unit, _enemy_unit = _battle_state(
        gsc_unit_id=gsc_unit_id,
        gsc_datasheet_id=gsc_datasheet_id,
        gsc_unit_name=gsc_unit_name,
        gsc_model_count=gsc_model_count,
        phase=BattlePhase.SHOOTING,
        active_player_id=ENEMY_PLAYER_ID,
        enemy_x=enemy_x,
        enemy_y=enemy_y,
    )
    decisions = DecisionController()
    request = _request_resurgence_for_destroyed_unit(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )
    result = DecisionResult.for_request(
        result_id=f"phase17g-gsc-spend:{destroyed_unit.unit_instance_id}",
        request=request,
        selected_option_id=_option_by_selection(request, "spend").option_id,
    )
    decisions.submit_result(result)
    apply_cult_ambush_resurgence_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    replacement = _unit_by_id(state, f"{destroyed_unit.unit_instance_id}:cult-ambush-001")
    return state, decisions, _next_request(decisions), replacement


def _state_waiting_for_ingress_placement() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
    UnitInstance,
]:
    state, decisions, marker_request, replacement = _state_waiting_for_marker_placement(
        gsc_unit_id=ACOLYTE_UNIT_ID,
        gsc_datasheet_id="acolyte-hybrids-with-autopistols",
        gsc_unit_name="Acolyte Hybrids with Autopistols",
        gsc_model_count=5,
        enemy_x=40.0,
        enemy_y=40.0,
    )
    marker_result = _marker_placement_result(
        request=marker_request,
        result_id="phase17g-gsc-marker-for-placement-helper",
        x_inches=8.0,
        y_inches=8.0,
    )
    decisions.submit_result(marker_result)
    apply_cult_ambush_marker_placement_decision(
        state=state,
        decisions=decisions,
        request=marker_request,
        result=marker_result,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    ingress_request = cult_ambush_marker_ingress_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )
    )
    assert ingress_request is not None
    ingress_result = DecisionResult.for_request(
        result_id="phase17g-gsc-select-placement-helper-ingress",
        request=ingress_request,
        selected_option_id=_option_by_selection(ingress_request, "ingress").option_id,
    )
    assert apply_cult_ambush_marker_ingress_selection(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=ingress_request,
            result=ingress_result,
        )
    )
    return state, decisions, _next_request(decisions), replacement


def _cult_ambush_placement_payload(
    *,
    proposal_request: MovementProposalRequest,
    unit: UnitInstance,
) -> PlacementProposalPayload:
    return PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=unit.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
        attempted_placement=_unit_placement_for_marker_unit(
            unit=unit,
            x_inches=8.0,
            y_inches=8.0,
        ),
    )


def _request_resurgence_for_destroyed_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    destroyed_unit: UnitInstance,
) -> DecisionRequest:
    _run_resurgence_hook(
        state=state,
        decisions=decisions,
        destroyed_unit=destroyed_unit,
    )
    return _next_request(decisions)


def _run_resurgence_hook(
    *,
    state: GameState,
    decisions: DecisionController,
    destroyed_unit: UnitInstance,
    destroying_player_id: str = ENEMY_PLAYER_ID,
    destroyed_player_id: str = GSC_PLAYER_ID,
) -> None:
    event = decisions.event_log.append(
        "model_destroyed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": state.current_battle_phase.value
                if state.current_battle_phase is not None
                else BattlePhase.SHOOTING.value,
                "destroying_player_id": destroying_player_id,
                "target_unit_instance_id": destroyed_unit.unit_instance_id,
                "model_instance_id": destroyed_unit.own_models[-1].model_instance_id,
            }
        ),
    )
    request_cult_ambush_resurgence(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=state.current_battle_phase or BattlePhase.SHOOTING,
            model_destroyed_event_id=event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], event.payload),
            destroying_player_id=destroying_player_id,
            destroyed_unit_instance_id=destroyed_unit.unit_instance_id,
            destroyed_player_id=destroyed_player_id,
        )
    )


def _marker_placement_result(
    *,
    request: DecisionRequest,
    result_id: str,
    x_inches: float,
    y_inches: float,
) -> DecisionResult:
    request_payload = cast(dict[str, JsonValue], request.payload)
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "request_id": request.request_id,
                "submission_kind": "cult_ambush_marker_placement",
                "marker_id": request_payload["marker_id"],
                "player_id": request.actor_id,
                "x_inches": x_inches,
                "y_inches": y_inches,
            }
        ),
    )


def _no_marker_result(*, request: DecisionRequest, result_id: str) -> DecisionResult:
    request_payload = cast(dict[str, JsonValue], request.payload)
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "request_id": request.request_id,
                "submission_kind": "cult_ambush_no_marker",
                "marker_id": request_payload["marker_id"],
                "player_id": request.actor_id,
                "no_marker_reason": "no_legal_marker_position",
            }
        ),
    )


def _marker(
    *,
    replacement_unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> CultAmbushMarker:
    return CultAmbushMarker(
        marker_id="cult-ambush-marker:phase17g-test",
        player_id=GSC_PLAYER_ID,
        replacement_unit_instance_id=replacement_unit_instance_id,
        source_destroyed_unit_instance_id=ACOLYTE_UNIT_ID,
        created_battle_round=1,
        created_phase=BattlePhase.SHOOTING,
        created_active_player_id=ENEMY_PLAYER_ID,
        x_inches=x_inches,
        y_inches=y_inches,
    )


def _army(
    *,
    army_id: str,
    player_id: str,
    faction_id: str,
    battle_size: BattleSize,
    units: tuple[UnitInstance, ...],
) -> ArmyDefinition:
    descriptor = _ruleset_descriptor()
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id="phase17g-gsc-catalog",
        source_package_id="phase17g-gsc-source-package",
        ruleset_id=descriptor.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(f"{faction_id}-detachment",),
        ),
        units=units,
        roster_legality_report=RosterLegalityReport(battle_size=battle_size),
        battle_size=battle_size,
    )


def _unit(
    *,
    unit_instance_id: str,
    datasheet_id: str,
    name: str,
    model_count: int,
    has_cult_ambush: bool,
    keywords: tuple[str, ...] = ("INFANTRY",),
) -> UnitInstance:
    models = tuple(
        _model(
            model_instance_id=f"{unit_instance_id}:model-{index:03d}",
            datasheet_id=datasheet_id,
            model_profile_id=f"{datasheet_id}:profile",
            keywords=keywords,
        )
        for index in range(1, model_count + 1)
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name=name,
        keywords=keywords,
        faction_keywords=("GENESTEALER CULTS",) if has_cult_ambush else ("ADEPTUS ASTARTES",),
        datasheet_abilities=(_cult_ambush_ability(),) if has_cult_ambush else (),
        datasheet_source_ids=(f"phase17g-gsc:datasheet:{datasheet_id}",),
        own_models=models,
        wargear_selections=(),
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    keywords: tuple[str, ...],
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(10.0)
    return ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=f"{model_instance_id} model",
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 2),
            CharacteristicValue.from_raw(Characteristic.SAVE, 5),
            CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 1),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=keywords,
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=2,
        wounds_remaining=1,
        wargear_ids=(ONE_SHOT_WARGEAR_ID,),
        source_ids=(f"phase17g-gsc:model:{model_profile_id}",),
    )


def _cult_ambush_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="cult-ambush",
        name="Cult Ambush",
        source_id=SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Genestealer Cults Cult Ambush.",
    )


def _unit_placement(
    *,
    army_id: str,
    player_id: str,
    unit: UnitInstance,
    x_inches: float,
    y_inches: float,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x_inches + index * 0.75, y_inches),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _unit_placement_for_marker_unit(
    *,
    unit: UnitInstance,
    x_inches: float,
    y_inches: float,
) -> UnitPlacement:
    offsets = ((0.0, 0.0), (0.75, 0.0), (-0.75, 0.0), (0.0, 0.75), (0.0, -0.75))
    return UnitPlacement(
        army_id=GSC_ARMY_ID,
        player_id=GSC_PLAYER_ID,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=GSC_ARMY_ID,
                player_id=GSC_PLAYER_ID,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x_inches + offsets[index][0], y_inches + offsets[index][1]),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _option_by_selection(request: DecisionRequest, selection: str) -> DecisionOption:
    for option in request.options:
        payload = option.payload
        if isinstance(payload, dict) and payload.get("selection") == selection:
            return option
    raise AssertionError(f"Missing option for selection {selection}.")


def _next_request(decisions: DecisionController) -> DecisionRequest:
    return decisions.queue.peek_next()


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"Missing unit {unit_instance_id}.")


def _replace_unit_in_state(state: GameState, replacement_unit: UnitInstance) -> None:
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replacement_unit
                if unit.unit_instance_id == replacement_unit.unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _violation_codes(result: ProposalValidationResult) -> set[str]:
    return {violation.violation_code for violation in result.violations}


def _ruleset_descriptor() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase17g-genestealer-cults-test"
    )


def _config_for_context(game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        ruleset_descriptor=_ruleset_descriptor(),
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(
                catalog=catalog,
                army_id=GSC_ARMY_ID,
                player_id=GSC_PLAYER_ID,
                faction_id=GENESTEALER_CULTS_FACTION_ID,
                unit_selection_id="config-gsc-unit",
            ),
            _muster_request(
                catalog=catalog,
                army_id=ENEMY_ARMY_ID,
                player_id=ENEMY_PLAYER_ID,
                faction_id="adeptus-astartes",
                unit_selection_id="config-enemy-unit",
            ),
        ),
        player_ids=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        turn_order=(GSC_PLAYER_ID, ENEMY_PLAYER_ID),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        allow_legacy_non_strict_rosters=True,
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(f"{faction_id}-detachment",),
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
