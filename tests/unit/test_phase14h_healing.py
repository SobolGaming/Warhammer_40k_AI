from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    AttachedUnitFormation,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementRecord,
    PlacementError,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    HealingEffect,
    HealingEffectPayload,
    HealingModelSelection,
    HealingStep,
    HealingStepKind,
    apply_healing_model_decision,
    apply_recorded_healing_model_decision,
    healing_effect_from_request,
    healing_step_kind_from_token,
    invalid_healing_model_decision_status,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_healing_iterates_wound_revival_revived_wound_and_no_effect() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    wounded = unit.own_models[0]
    removed = unit.own_models[1]
    assert wounded.starting_wounds == 2
    _set_model_wounds(state, model_instance_id=wounded.model_instance_id, wounds_remaining=1)
    revival_placement = _remove_model(state, model_instance_id=removed.model_instance_id)
    effect = HealingEffect(
        effect_id="phase14h-heal-sequence",
        target_unit_instance_id=unit_id,
        amount=4,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
        revival_placements=(revival_placement,),
    )

    resolved, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )

    assert request is None
    assert resolved.is_complete()
    assert [step.step_kind for step in resolved.resolved_steps] == [
        HealingStepKind.HEAL_WOUND,
        HealingStepKind.REVIVE_MODEL,
        HealingStepKind.HEAL_WOUND,
        HealingStepKind.NO_EFFECT,
    ]
    assert (
        model_by_id(state=state, model_instance_id=wounded.model_instance_id).wounds_remaining
        == wounded.starting_wounds
    )
    revived = model_by_id(state=state, model_instance_id=removed.model_instance_id)
    assert revived.wounds_remaining == revived.starting_wounds
    assert state.battlefield_state is not None
    assert removed.model_instance_id in state.battlefield_state.placed_model_ids()
    assert removed.model_instance_id not in state.battlefield_state.removed_model_ids
    assert HealingEffect.from_payload(resolved.to_payload()).to_payload() == resolved.to_payload()
    assert "<" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_attached_unit_multiple_wounded_models_use_opposing_healing_decision() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    bodyguard_id = unit.own_models[0].model_instance_id
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-heal-attached-wounded",
        target_unit_instance_id=unit_id,
        amount=3,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )

    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert blocked.resolved_steps == ()
    assert request is not None
    assert request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert _option_model_ids(request) == (bodyguard_id, leader_id)

    result = DecisionResult.for_request(
        result_id="phase14h-heal-attached-leader-result",
        request=request,
        selected_option_id=_option_for_model(request, leader_id).option_id,
    )
    resolved, follow_up = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=blocked,
        result=result,
    )

    assert follow_up is None
    assert resolved.is_complete()
    assert [step.step_kind for step in resolved.resolved_steps] == [
        HealingStepKind.HEAL_WOUND,
        HealingStepKind.HEAL_WOUND,
        HealingStepKind.NO_EFFECT,
    ]
    assert resolved.resolved_steps[0].model_instance_id == leader_id
    assert resolved.resolved_steps[1].model_instance_id == bodyguard_id
    assert decisions.queue.pending_requests == ()
    assert len(decisions.records) == 1
    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 2
    assert model_by_id(state=state, model_instance_id=bodyguard_id).wounds_remaining == 2


def test_healing_selection_drift_rejects_before_queue_pop() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    bodyguard_id = unit.own_models[0].model_instance_id
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-heal-stale",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    _set_model_wounds(state, model_instance_id=bodyguard_id, wounds_remaining=2)
    result = DecisionResult.for_request(
        result_id="phase14h-heal-stale-result",
        request=request,
        selected_option_id=_option_for_model(request, leader_id).option_id,
    )

    with pytest.raises(GameLifecycleError, match="stale"):
        apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=blocked,
            result=result,
        )

    assert decisions.queue.pending_requests == (request,)
    assert decisions.records == ()
    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 1


def test_mustered_attached_unit_heals_then_revives_destroyed_bodyguard_component() -> None:
    state = _battle_state(config=_config(attached_alpha=True))
    decisions = DecisionController()
    formation = state.army_definitions[0].attached_units[0]
    attached_id = formation.attached_unit_instance_id
    bodyguard = _unit_by_id(state, formation.bodyguard_unit_instance_id)
    leader = _unit_by_id(state, formation.leader_unit_instance_ids[0])
    support = _unit_by_id(state, formation.support_unit_instance_ids[0])
    leader_model = leader.own_models[0]
    support_model = support.own_models[0]
    _set_model_wounds(
        state,
        model_instance_id=leader_model.model_instance_id,
        wounds_remaining=leader_model.starting_wounds - 1,
    )
    for model in bodyguard.own_models:
        _remove_model(state, model_instance_id=model.model_instance_id)
    assert state.battlefield_state is not None
    with pytest.raises(GameLifecycleError, match="StartingStrengthRecord"):
        state.starting_strength_record_for_unit(bodyguard.unit_instance_id)
    state.battlefield_state.unit_placement_by_id(leader.unit_instance_id)
    state.battlefield_state.unit_placement_by_id(support.unit_instance_id)
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(bodyguard.unit_instance_id)
    leader_placement = state.battlefield_state.model_placement_by_id(leader_model.model_instance_id)
    revived_model = bodyguard.own_models[0]
    revival_placements = tuple(
        ModelPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id=bodyguard.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(
                leader_placement.pose.position.x + 0.5 + (index * 0.1),
                leader_placement.pose.position.y,
                leader_placement.pose.position.z,
            ),
        )
        for index, model in enumerate(bodyguard.own_models)
    )
    effect = HealingEffect(
        effect_id="phase14h-real-attached-heal-revive",
        target_unit_instance_id=attached_id,
        amount=2,
        opposing_player_id="player-b",
        phase_start_model_ids=(leader_model.model_instance_id, support_model.model_instance_id),
        revival_placements=revival_placements,
    )

    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )

    assert request is not None
    assert blocked.resolved_steps[0].step_kind is HealingStepKind.HEAL_WOUND
    assert blocked.resolved_steps[0].model_instance_id == leader_model.model_instance_id
    assert _option_model_ids(request) == tuple(
        sorted(model.model_instance_id for model in bodyguard.own_models)
    )

    resolved, follow_up = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=blocked,
        result=DecisionResult.for_request(
            result_id="phase14h-real-attached-heal-revive-result",
            request=request,
            selected_option_id=_option_for_model(
                request,
                revived_model.model_instance_id,
            ).option_id,
        ),
    )

    assert follow_up is None
    assert resolved.is_complete()
    assert [step.step_kind for step in resolved.resolved_steps] == [
        HealingStepKind.HEAL_WOUND,
        HealingStepKind.REVIVE_MODEL,
    ]
    assert (
        model_by_id(state=state, model_instance_id=revived_model.model_instance_id).wounds_remaining
        == 1
    )
    bodyguard_placement = state.battlefield_state.unit_placement_by_id(bodyguard.unit_instance_id)
    assert bodyguard_placement.model_placements[0].model_instance_id == (
        revived_model.model_instance_id
    )
    assert bodyguard_placement.model_placements[0].unit_instance_id == bodyguard.unit_instance_id
    assert state.starting_strength_record_for_unit(attached_id).starting_model_count == 7
    with pytest.raises(GameLifecycleError, match="attached-unit identity"):
        resolve_healing_until_blocked(
            state=state,
            decisions=DecisionController(),
            ruleset_descriptor=_ruleset(),
            effect=replace(effect, target_unit_instance_id=bodyguard.unit_instance_id),
        )


def test_mustered_attached_unit_healing_stale_candidates_reject_before_queue_pop() -> None:
    state = _battle_state(config=_config(attached_alpha=True))
    decisions = DecisionController()
    formation = state.army_definitions[0].attached_units[0]
    leader = _unit_by_id(state, formation.leader_unit_instance_ids[0])
    support = _unit_by_id(state, formation.support_unit_instance_ids[0])
    leader_model = leader.own_models[0]
    support_model = support.own_models[0]
    _set_model_wounds(
        state,
        model_instance_id=leader_model.model_instance_id,
        wounds_remaining=leader_model.starting_wounds - 1,
    )
    _set_model_wounds(
        state,
        model_instance_id=support_model.model_instance_id,
        wounds_remaining=support_model.starting_wounds - 1,
    )
    effect = HealingEffect(
        effect_id="phase14h-real-attached-heal-stale",
        target_unit_instance_id=formation.attached_unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_attached_rules_unit_placed_model_ids(state, formation),
    )
    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    assert _option_model_ids(request) == (
        leader_model.model_instance_id,
        support_model.model_instance_id,
    )
    _set_model_wounds(
        state,
        model_instance_id=leader_model.model_instance_id,
        wounds_remaining=leader_model.starting_wounds,
    )

    with pytest.raises(GameLifecycleError, match="stale"):
        apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=blocked,
            result=DecisionResult.for_request(
                result_id="phase14h-real-attached-heal-stale-result",
                request=request,
                selected_option_id=_option_for_model(
                    request,
                    support_model.model_instance_id,
                ).option_id,
            ),
        )

    assert decisions.queue.pending_requests == (request,)
    assert decisions.records == ()
    assert (
        model_by_id(
            state=state,
            model_instance_id=support_model.model_instance_id,
        ).wounds_remaining
        == support_model.starting_wounds - 1
    )


def test_lifecycle_submit_healing_model_decision_routes_through_submit_decision() -> None:
    state = _battle_state()
    lifecycle = _lifecycle_for_state(state)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    state = lifecycle_state
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    bodyguard_id = unit.own_models[0].model_instance_id
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-lifecycle-healing",
        target_unit_instance_id=unit_id,
        amount=2,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert (
        HealingEffect.from_payload(
            cast(HealingEffectPayload, request_payload["effect"])
        ).to_payload()
        == effect.to_payload()
    )
    pending_request = lifecycle.decision_controller.queue.peek_next()

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14h-lifecycle-healing-result",
            request=pending_request,
            selected_option_id=_option_for_model(pending_request, leader_id).option_id,
        )
    )

    assert status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    }
    assert lifecycle.decision_controller.records[-1].request.decision_type == (
        SELECT_HEALING_MODEL_DECISION_TYPE
    )
    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 2
    assert model_by_id(state=state, model_instance_id=bodyguard_id).wounds_remaining == 2
    assert not any(
        request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
        for request in lifecycle.decision_controller.queue.pending_requests
    )


def test_lifecycle_healing_selection_stale_rejects_before_queue_pop() -> None:
    state = _battle_state()
    lifecycle = _lifecycle_for_state(state)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    state = lifecycle_state
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    bodyguard_id = unit.own_models[0].model_instance_id
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-lifecycle-healing-stale",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    _set_model_wounds(state, model_instance_id=bodyguard_id, wounds_remaining=2)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14h-lifecycle-healing-stale-result",
            request=request,
            selected_option_id=_option_for_model(request, leader_id).option_id,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {
        "invalid_reason": "invalid_healing_model_selection_result",
        "field": "legal_model_ids",
    }
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.decision_controller.records == ()
    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 1


def test_lifecycle_healing_model_decision_returns_follow_up_request_for_next_choice() -> None:
    state = _battle_state()
    lifecycle = _lifecycle_for_state(state)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    state = lifecycle_state
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    removed = tuple(
        _remove_model(state, model_instance_id=model.model_instance_id)
        for model in unit.own_models[:3]
    )
    effect = HealingEffect(
        effect_id="phase14h-lifecycle-healing-follow-up",
        target_unit_instance_id=unit_id,
        amount=3,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
        revival_placements=removed,
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    selected_model_id = removed[2].model_instance_id

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14h-lifecycle-healing-follow-up-result",
            request=request,
            selected_option_id=_option_for_model(request, selected_model_id).option_id,
        )
    )
    follow_up_request = lifecycle.decision_controller.queue.peek_next()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request == follow_up_request
    assert status.payload == {
        "decision_type": SELECT_HEALING_MODEL_DECISION_TYPE,
        "effect_id": effect.effect_id,
        "target_unit_instance_id": unit_id,
    }
    assert follow_up_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert model_by_id(state=state, model_instance_id=selected_model_id).wounds_remaining == 2


def test_healing_lifecycle_validation_helpers_cover_invalid_finite_fields() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-healing-helper-validation",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    option = _option_for_model(request, leader_id)

    wrong_request_id = DecisionResult(
        request_id="phase14h-healing-wrong-request",
        result_id="phase14h-healing-wrong-request",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=option.option_id,
        payload=option.payload,
    )
    wrong_actor = DecisionResult(
        request_id=request.request_id,
        result_id="phase14h-healing-wrong-actor",
        decision_type=request.decision_type,
        actor_id="player-a",
        selected_option_id=option.option_id,
        payload=option.payload,
    )
    wrong_option = DecisionResult(
        request_id=request.request_id,
        result_id="phase14h-healing-wrong-option",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="phase14h-healing-missing-option",
        payload=option.payload,
    )
    wrong_payload = DecisionResult(
        request_id=request.request_id,
        result_id="phase14h-healing-wrong-payload",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=option.option_id,
        payload={"source_id": None},
    )

    def invalid_field(result: DecisionResult) -> object:
        status = invalid_healing_model_decision_status(
            state=state,
            request=request,
            result=result,
        )
        assert status is not None
        return cast(dict[str, object], status.payload)["field"]

    assert healing_effect_from_request(request=request).to_payload() == effect.to_payload()
    assert invalid_field(wrong_request_id) == "request_id"
    assert invalid_field(wrong_actor) == "actor_id"
    assert invalid_field(wrong_option) == "selected_option_id"
    assert invalid_field(wrong_payload) == "payload"


def test_healing_request_routing_rejects_malformed_request_contexts() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-healing-malformed-routing",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    option = _option_for_model(request, leader_id)
    result = DecisionResult.for_request(
        result_id="phase14h-healing-malformed-routing-result",
        request=request,
        selected_option_id=option.option_id,
    )
    wrong_decision_type = DecisionResult(
        request_id=request.request_id,
        result_id="phase14h-healing-wrong-decision-type",
        decision_type="wrong_healing_result_type",
        actor_id=request.actor_id,
        selected_option_id=option.option_id,
        payload=option.payload,
    )

    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        healing_effect_from_request(request=cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="requires a healing request"):
        healing_effect_from_request(
            request=replace(request, decision_type="wrong_healing_request_type")
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        healing_effect_from_request(request=replace(request, payload=None))
    with pytest.raises(GameLifecycleError, match="payload missing effect"):
        healing_effect_from_request(request=replace(request, payload={}))
    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        invalid_healing_model_decision_status(
            state=state,
            request=cast(DecisionRequest, object()),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="requires a healing request"):
        invalid_healing_model_decision_status(
            state=state,
            request=replace(request, decision_type="wrong_healing_request_type"),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="requires a DecisionResult"):
        invalid_healing_model_decision_status(
            state=state,
            request=request,
            result=cast(DecisionResult, object()),
        )

    status = invalid_healing_model_decision_status(
        state=state,
        request=request,
        result=wrong_decision_type,
    )

    assert status is not None
    assert status.payload == {
        "invalid_reason": "invalid_healing_model_selection_result",
        "field": "decision_type",
    }


@pytest.mark.parametrize(
    ("field_name", "replacement_value", "expected_field"),
    [
        ("effect_id", "phase14h-healing-stale-effect", "effect_id"),
        ("target_unit_instance_id", "phase14h-healing-stale-target", "target_unit_instance_id"),
        ("step_index", 2, "step_index"),
        ("source_rule_id", "phase14h-healing-stale-source", "source_rule_id"),
        ("source_context", {"phase14h": "stale"}, "source_context"),
        ("selection_kind", HealingStepKind.REVIVE_MODEL.value, "selection_kind"),
    ],
)
def test_healing_lifecycle_validation_reports_stale_selection_fields(
    field_name: str,
    replacement_value: JsonValue,
    expected_field: str,
) -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-healing-stale-selection-fields",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    option = _option_for_model(request, leader_id)
    option_payload = dict(cast(dict[str, JsonValue], option.payload))
    option_payload[field_name] = replacement_value
    if field_name == "selection_kind":
        assert state.battlefield_state is not None
        option_payload["revival_placement"] = cast(
            JsonValue,
            state.battlefield_state.model_placement_by_id(leader_id).to_payload(),
        )
    drifted_option = replace(option, payload=option_payload)
    drifted_request = replace(request, options=(drifted_option,))
    result = DecisionResult.for_request(
        result_id=f"phase14h-healing-stale-selection-{expected_field}",
        request=drifted_request,
        selected_option_id=drifted_option.option_id,
    )

    status = invalid_healing_model_decision_status(
        state=state,
        request=drifted_request,
        result=result,
    )

    assert status is not None
    assert status.payload == {
        "invalid_reason": "invalid_healing_model_selection_result",
        "field": expected_field,
    }


def test_recorded_healing_model_decision_rejects_effect_drift_without_mutation() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-recorded-healing",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase14h-recorded-healing-result",
        request=request,
        selected_option_id=_option_for_model(request, leader_id).option_id,
    )
    decisions.submit_result(result)

    with pytest.raises(GameLifecycleError, match="effect drift"):
        apply_recorded_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            request=request,
            result=result,
            effect=HealingEffect(
                effect_id="phase14h-recorded-healing-drift",
                target_unit_instance_id=unit_id,
                amount=1,
                opposing_player_id="player-b",
                phase_start_model_ids=_placed_model_ids(state, unit_id),
            ),
        )

    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 1


def test_recorded_healing_model_decision_can_replay_from_request_effect() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    leader_id = unit.own_models[1].model_instance_id
    effect = HealingEffect(
        effect_id="phase14h-recorded-healing-request-effect",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    _blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase14h-recorded-healing-request-effect-result",
        request=request,
        selected_option_id=_option_for_model(request, leader_id).option_id,
    )
    decisions.submit_result(result)

    resolved, follow_up = apply_recorded_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        request=request,
        result=result,
    )

    assert follow_up is None
    assert resolved.is_complete()
    assert model_by_id(state=state, model_instance_id=leader_id).wounds_remaining == 2


def test_multiple_wounded_non_attached_unit_rejects_without_choice() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    _set_model_wounds(
        state,
        model_instance_id=unit.own_models[0].model_instance_id,
        wounds_remaining=1,
    )
    _set_model_wounds(
        state,
        model_instance_id=unit.own_models[1].model_instance_id,
        wounds_remaining=1,
    )
    effect = HealingEffect(
        effect_id="phase14h-heal-non-attached-multiple",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )

    with pytest.raises(GameLifecycleError, match="attached-unit healing decision"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=effect,
        )

    assert decisions.queue.pending_requests == ()
    assert decisions.records == ()


def test_revival_requires_explicit_candidate_placement_without_mutation() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    removed_placement = _remove_model(state, model_instance_id=unit.own_models[0].model_instance_id)
    effect = HealingEffect(
        effect_id="phase14h-revive-missing-placement",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )

    with pytest.raises(GameLifecycleError, match="missing placement"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=effect,
        )

    assert state.battlefield_state is not None
    assert removed_placement.model_instance_id in state.battlefield_state.removed_model_ids
    assert (
        model_by_id(
            state=state,
            model_instance_id=removed_placement.model_instance_id,
        ).wounds_remaining
        == 0
    )
    assert decisions.queue.pending_requests == ()


def test_malformed_healing_selection_rejects_before_queue_pop() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _replace_with_attached_wounded_unit(state, unit_id=unit_id)
    effect = HealingEffect(
        effect_id="phase14h-heal-malformed",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )
    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    selected_option = _option_for_model(request, unit.own_models[0].model_instance_id)
    malformed = DecisionResult(
        request_id=request.request_id,
        result_id="phase14h-heal-malformed-result",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=selected_option.option_id,
        payload={
            "submission_kind": SELECT_HEALING_MODEL_DECISION_TYPE,
            "selection_kind": HealingStepKind.HEAL_WOUND.value,
            "effect_id": blocked.effect_id,
            "target_unit_instance_id": blocked.target_unit_instance_id,
            "step_index": blocked.next_step_index(),
            "model_instance_id": unit.own_models[0].model_instance_id,
            "legal_model_ids": selected_option.option_id,
            "source_rule_id": blocked.source_rule_id,
            "source_context": blocked.source_context,
            "revival_placement": None,
        },
    )

    with pytest.raises(DecisionError, match="payload must match"):
        apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=blocked,
            result=malformed,
        )

    assert decisions.queue.pending_requests == (request,)
    assert decisions.records == ()


def test_multiple_missing_models_use_opposing_revival_decision() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    first_removed = _remove_model(state, model_instance_id=unit.own_models[0].model_instance_id)
    second_removed = _remove_model(state, model_instance_id=unit.own_models[1].model_instance_id)
    effect = HealingEffect(
        effect_id="phase14h-revive-choice",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
        revival_placements=(first_removed, second_removed),
    )

    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=effect,
    )
    assert request is not None
    assert request.actor_id == "player-b"
    selected_model_id = second_removed.model_instance_id
    result = DecisionResult.for_request(
        result_id="phase14h-revive-choice-result",
        request=request,
        selected_option_id=_option_for_model(request, selected_model_id).option_id,
    )
    resolved, follow_up = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=blocked,
        result=result,
    )

    assert follow_up is None
    assert resolved.resolved_steps[0].step_kind is HealingStepKind.REVIVE_MODEL
    assert resolved.resolved_steps[0].model_instance_id == selected_model_id
    assert model_by_id(state=state, model_instance_id=selected_model_id).wounds_remaining == 1
    assert state.battlefield_state is not None
    assert selected_model_id in state.battlefield_state.placed_model_ids()
    assert selected_model_id not in state.battlefield_state.removed_model_ids
    assert first_removed.model_instance_id in state.battlefield_state.removed_model_ids


def test_revival_requires_phase_start_coherent_placement_without_mutation() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    removed_placement = _remove_model(state, model_instance_id=unit.own_models[0].model_instance_id)
    invalid_placement = removed_placement.with_pose(
        Pose.at(x=70.0, y=70.0, z=0.0, facing_degrees=0.0)
    )
    effect = HealingEffect(
        effect_id="phase14h-revive-invalid-placement",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
        revival_placements=(invalid_placement,),
    )

    with pytest.raises(GameLifecycleError, match=r"coherency|coherent"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=effect,
        )

    assert (
        model_by_id(
            state=state,
            model_instance_id=removed_placement.model_instance_id,
        ).wounds_remaining
        == 0
    )
    assert state.battlefield_state is not None
    assert removed_placement.model_instance_id in state.battlefield_state.removed_model_ids
    assert removed_placement.model_instance_id not in state.battlefield_state.placed_model_ids()


def test_healing_domain_records_fail_fast_on_invalid_payload_shapes() -> None:
    state = _battle_state()
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    model_id = unit.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_by_id(model_id)
    transition_batch = BattlefieldTransitionBatch(
        placements=(
            ModelPlacementRecord(
                model_instance_id=model_id,
                placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
                pose=placement.pose,
            ),
        )
    )
    valid_step = HealingStep(
        step_index=1,
        step_kind=HealingStepKind.HEAL_WOUND,
        model_instance_id=model_id,
        starting_wounds_remaining=1,
        final_wounds_remaining=2,
    )

    with pytest.raises(GameLifecycleError, match="must not select a model"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.NO_EFFECT,
            model_instance_id=model_id,
            starting_wounds_remaining=None,
            final_wounds_remaining=None,
        )
    with pytest.raises(GameLifecycleError, match="must not include wounds"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.NO_EFFECT,
            model_instance_id=None,
            starting_wounds_remaining=1,
            final_wounds_remaining=None,
        )
    with pytest.raises(GameLifecycleError, match="must select a model"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.HEAL_WOUND,
            model_instance_id=None,
            starting_wounds_remaining=1,
            final_wounds_remaining=2,
        )
    with pytest.raises(GameLifecycleError, match="must include wound transition state"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.HEAL_WOUND,
            model_instance_id=model_id,
            starting_wounds_remaining=None,
            final_wounds_remaining=2,
        )
    with pytest.raises(GameLifecycleError, match="must not include placement"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.HEAL_WOUND,
            model_instance_id=model_id,
            starting_wounds_remaining=1,
            final_wounds_remaining=2,
            transition_batch=transition_batch,
        )
    with pytest.raises(GameLifecycleError, match="requires placement"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.REVIVE_MODEL,
            model_instance_id=model_id,
            starting_wounds_remaining=0,
            final_wounds_remaining=1,
        )
    with pytest.raises(GameLifecycleError, match="BattlefieldTransitionBatch"):
        HealingStep(
            step_index=1,
            step_kind=HealingStepKind.HEAL_WOUND,
            model_instance_id=model_id,
            starting_wounds_remaining=1,
            final_wounds_remaining=2,
            transition_batch=cast(BattlefieldTransitionBatch, object()),
        )

    with pytest.raises(GameLifecycleError, match="revival_placements must be a tuple"):
        HealingEffect(
            effect_id="phase14h-invalid-revival-placement-list",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            revival_placements=cast(tuple[ModelPlacement, ...], [placement]),
        )
    with pytest.raises(GameLifecycleError, match="must be unique"):
        HealingEffect(
            effect_id="phase14h-invalid-revival-placement-duplicate",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            revival_placements=(placement, placement),
        )
    with pytest.raises(GameLifecycleError, match="must contain placements"):
        HealingEffect(
            effect_id="phase14h-invalid-revival-placement-value",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            revival_placements=cast(tuple[ModelPlacement, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="resolved_steps must be a tuple"):
        HealingEffect(
            effect_id="phase14h-invalid-step-list",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            resolved_steps=cast(tuple[HealingStep, ...], [valid_step]),
        )
    with pytest.raises(GameLifecycleError, match="must contain HealingStep"):
        HealingEffect(
            effect_id="phase14h-invalid-step-value",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            resolved_steps=cast(tuple[HealingStep, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="must be sequential"):
        HealingEffect(
            effect_id="phase14h-invalid-step-sequence",
            target_unit_instance_id=unit_id,
            amount=2,
            opposing_player_id="player-b",
            resolved_steps=(
                HealingStep(
                    step_index=2,
                    step_kind=HealingStepKind.HEAL_WOUND,
                    model_instance_id=model_id,
                    starting_wounds_remaining=1,
                    final_wounds_remaining=2,
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="exceed amount"):
        HealingEffect(
            effect_id="phase14h-invalid-step-overflow",
            target_unit_instance_id=unit_id,
            amount=1,
            opposing_player_id="player-b",
            resolved_steps=(
                valid_step,
                HealingStep(
                    step_index=2,
                    step_kind=HealingStepKind.HEAL_WOUND,
                    model_instance_id=model_id,
                    starting_wounds_remaining=1,
                    final_wounds_remaining=2,
                ),
            ),
        )
    complete_effect = HealingEffect(
        effect_id="phase14h-complete-effect",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        resolved_steps=(valid_step,),
    )
    with pytest.raises(GameLifecycleError, match="already complete"):
        complete_effect.next_step_index()
    with pytest.raises(GameLifecycleError, match="step must be a HealingStep"):
        complete_effect.with_step(cast(HealingStep, object()))
    with pytest.raises(GameLifecycleError, match="step_index drift"):
        HealingEffect(
            effect_id="phase14h-incomplete-effect",
            target_unit_instance_id=unit_id,
            amount=2,
            opposing_player_id="player-b",
        ).with_step(
            HealingStep(
                step_index=2,
                step_kind=HealingStepKind.HEAL_WOUND,
                model_instance_id=model_id,
                starting_wounds_remaining=1,
                final_wounds_remaining=2,
            )
        )

    with pytest.raises(GameLifecycleError, match="cannot select no_effect"):
        HealingModelSelection(
            request_id="phase14h-selection-request",
            result_id="phase14h-selection-result",
            player_id="player-b",
            selection_kind=HealingStepKind.NO_EFFECT,
            effect_id="phase14h-selection-effect",
            target_unit_instance_id=unit_id,
            step_index=1,
            selected_model_id=model_id,
            legal_model_ids=(model_id,),
            source_rule_id="phase14h-selection-source",
            source_context=None,
        )
    with pytest.raises(GameLifecycleError, match="selected model is not legal"):
        HealingModelSelection(
            request_id="phase14h-selection-request",
            result_id="phase14h-selection-result",
            player_id="player-b",
            selection_kind=HealingStepKind.HEAL_WOUND,
            effect_id="phase14h-selection-effect",
            target_unit_instance_id=unit_id,
            step_index=1,
            selected_model_id=model_id,
            legal_model_ids=("phase14h-other-model",),
            source_rule_id="phase14h-selection-source",
            source_context=None,
        )
    with pytest.raises(GameLifecycleError, match="revive requires placement"):
        HealingModelSelection(
            request_id="phase14h-selection-request",
            result_id="phase14h-selection-result",
            player_id="player-b",
            selection_kind=HealingStepKind.REVIVE_MODEL,
            effect_id="phase14h-selection-effect",
            target_unit_instance_id=unit_id,
            step_index=1,
            selected_model_id=model_id,
            legal_model_ids=(model_id,),
            source_rule_id="phase14h-selection-source",
            source_context=None,
        )
    with pytest.raises(GameLifecycleError, match="revival_placement must be a placement"):
        HealingModelSelection(
            request_id="phase14h-selection-request",
            result_id="phase14h-selection-result",
            player_id="player-b",
            selection_kind=HealingStepKind.REVIVE_MODEL,
            effect_id="phase14h-selection-effect",
            target_unit_instance_id=unit_id,
            step_index=1,
            selected_model_id=model_id,
            legal_model_ids=(model_id,),
            source_rule_id="phase14h-selection-source",
            source_context=None,
            revival_placement=cast(ModelPlacement, object()),
        )
    with pytest.raises(GameLifecycleError, match="heal must not include placement"):
        HealingModelSelection(
            request_id="phase14h-selection-request",
            result_id="phase14h-selection-result",
            player_id="player-b",
            selection_kind=HealingStepKind.HEAL_WOUND,
            effect_id="phase14h-selection-effect",
            target_unit_instance_id=unit_id,
            step_index=1,
            selected_model_id=model_id,
            legal_model_ids=(model_id,),
            source_rule_id="phase14h-selection-source",
            source_context=None,
            revival_placement=placement,
        )
    wrong_request = DecisionRequest(
        request_id="phase14h-wrong-selection-request",
        decision_type="wrong_healing_decision_type",
        actor_id="player-b",
        payload=None,
        options=(
            DecisionOption(
                option_id="wrong-healing-option",
                label="Wrong",
                payload=None,
            ),
        ),
    )
    wrong_result = DecisionResult(
        request_id=wrong_request.request_id,
        result_id="phase14h-wrong-selection-result",
        decision_type=wrong_request.decision_type,
        actor_id=wrong_request.actor_id,
        selected_option_id="wrong-healing-option",
        payload=None,
    )
    with pytest.raises(GameLifecycleError, match="requires a healing request"):
        HealingModelSelection.from_result(request=wrong_request, result=wrong_result)


def test_healing_public_entrypoints_reject_wrong_contexts() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    effect = HealingEffect(
        effect_id="phase14h-invalid-entrypoint",
        target_unit_instance_id=unit_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=_placed_model_ids(state, unit_id),
    )

    with pytest.raises(GameLifecycleError, match="DecisionController"):
        resolve_healing_until_blocked(
            state=state,
            decisions=cast(DecisionController, object()),
            ruleset_descriptor=_ruleset(),
            effect=effect,
        )
    with pytest.raises(GameLifecycleError, match="RulesetDescriptor"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            effect=effect,
        )
    with pytest.raises(GameLifecycleError, match="opposing player is not in this game"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=HealingEffect(
                effect_id="phase14h-invalid-player",
                target_unit_instance_id=unit_id,
                amount=1,
                opposing_player_id="player-c",
            ),
        )
    with pytest.raises(GameLifecycleError, match="cannot control the target unit"):
        resolve_healing_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=HealingEffect(
                effect_id="phase14h-owner-player",
                target_unit_instance_id=unit_id,
                amount=1,
                opposing_player_id="player-a",
            ),
        )

    with pytest.raises(GameLifecycleError, match="DecisionController"):
        apply_healing_model_decision(
            state=state,
            decisions=cast(DecisionController, object()),
            ruleset_descriptor=_ruleset(),
            effect=effect,
            result=cast(DecisionResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="RulesetDescriptor"):
        apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            effect=effect,
            result=cast(DecisionResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="DecisionResult"):
        apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset(),
            effect=effect,
            result=cast(DecisionResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        healing_step_kind_from_token(object())
    with pytest.raises(GameLifecycleError, match="Unsupported HealingStepKind token"):
        healing_step_kind_from_token("unsupported-healing-step")


def _replace_with_attached_wounded_unit(state: GameState, *, unit_id: str) -> UnitInstance:
    unit = _unit_by_id(state, unit_id)
    bodyguard = _with_attached_role(
        replace(unit.own_models[0], wounds_remaining=1),
        role="bodyguard",
    )
    leader = _with_attached_role(
        replace(unit.own_models[1], wounds_remaining=1),
        role="leader",
    )
    replacement = replace(
        unit,
        keywords=tuple(sorted({*unit.keywords, "ATTACHED_UNIT"})),
        own_models=(bodyguard, leader, *unit.own_models[2:]),
    )
    _replace_unit(state=state, replacement=replacement)
    return replacement


def _with_attached_role(model: ModelInstance, *, role: str) -> ModelInstance:
    source_ids = {
        source_id
        for source_id in model.source_ids
        if not source_id.startswith(("attached-role:", "runtime-attached-unit:"))
    }
    source_ids.add(f"runtime-attached-unit:{role}")
    if role in {"leader", "support"}:
        source_ids.add(f"attached-role:{role}")
    return replace(model, source_ids=tuple(sorted(source_ids)))


def _remove_model(state: GameState, *, model_instance_id: str) -> ModelPlacement:
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_by_id(model_instance_id)
    _set_model_wounds(state, model_instance_id=model_instance_id, wounds_remaining=0)
    state.battlefield_state = state.battlefield_state.with_removed_models((model_instance_id,))
    return placement


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"missing model {model_instance_id}")
    state.army_definitions = updated_armies


def _replace_unit(*, state: GameState, replacement: UnitInstance) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"missing unit {replacement.unit_instance_id}")


def _placed_model_ids(state: GameState, unit_id: str) -> tuple[str, ...]:
    assert state.battlefield_state is not None
    return tuple(
        placement.model_instance_id
        for placement in state.battlefield_state.unit_placement_by_id(unit_id).model_placements
    )


def _attached_rules_unit_placed_model_ids(
    state: GameState,
    formation: AttachedUnitFormation,
) -> tuple[str, ...]:
    assert state.battlefield_state is not None
    return tuple(
        sorted(
            placement.model_instance_id
            for unit_id in formation.component_unit_instance_ids
            for placement in state.battlefield_state.unit_placement_by_id(unit_id).model_placements
        )
    )


def _option_model_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(cast(dict[str, JsonValue], option.payload), key="model_instance_id")
            for option in request.options
        )
    )


def _option_for_model(request: DecisionRequest, model_instance_id: str) -> DecisionOption:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if payload["model_instance_id"] == model_instance_id:
            return option
    raise AssertionError(f"missing option for model {model_instance_id}")


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    assert type(value) is str
    return value


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _battle_state(*, config: GameConfig | None = None) -> GameState:
    config = _config() if config is None else config
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase14h-healing-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _lifecycle_for_state(state: GameState) -> GameLifecycle:
    config = _config()
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": {"frames": []},
        }
    )


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _config(*, attached_alpha: bool = False) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha_request = (
        _attached_alpha_army_muster_request(catalog=catalog)
        if attached_alpha
        else _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selection_id="intercessor-unit-1",
        )
    )
    return GameConfig(
        game_id="phase14h-healing-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            alpha_request,
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-3",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _attached_alpha_army_muster_request(*, catalog: ArmyCatalog) -> ArmyMusterRequest:
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-support",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase14h-healing-test"
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


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
