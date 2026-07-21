from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import healing_source_context as hctx
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementRecord,
    PlacedArmy,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import model_by_id, unit_owner_player_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingEffectPayload,
    HealingStep,
    HealingStepKind,
    healing_army_definitions_with_model_wounds,
    healing_revival_candidate_model_ids,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.movement_proposals import (
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.return_placement_legality import (
    validate_returned_model_endpoints,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyError,
    rules_unit_coherency_result,
)
from warhammer40k_core.geometry.pose import GeometryError

SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE = "submit_healing_revival_placement"


class HealingRevivalRequestPayload(TypedDict):
    submission_kind: str
    proposal_kind: str
    effect: HealingEffectPayload
    step_index: int
    model_instance_id: str
    component_unit_instance_id: str
    source_selection_request_id: str | None
    source_selection_result_id: str | None


@dataclass(frozen=True, slots=True)
class ValidatedHealingRevival:
    effect: HealingEffect
    model_instance_id: str
    starting_wounds_remaining: int
    final_wounds_remaining: int
    placement: ModelPlacement
    hypothetical_armies: tuple[ArmyDefinition, ...]
    hypothetical_battlefield: BattlefieldRuntimeState
    transition_batch: BattlefieldTransitionBatch


def request_healing_revival_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    effect: HealingEffect,
    model_instance_id: str,
    source_selection_request_id: str | None,
    source_selection_result_id: str | None,
) -> DecisionRequest:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Healing revival requires a DecisionController.")
    candidates = healing_revival_candidate_model_ids(state=state, effect=effect)
    if model_instance_id not in candidates:
        raise GameLifecycleError("Healing revival model is not a current candidate.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    component_id = rules_unit.component_unit_id_for_model(model_instance_id)
    owner_id = unit_owner_player_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    step_index = effect.next_step_index()
    request = DecisionRequest(
        request_id=f"{effect.effect_id}:healing-step-{step_index:03d}:placement",
        decision_type=SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
        actor_id=owner_id,
        payload=validate_json_value(
            HealingRevivalRequestPayload(
                submission_kind=SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
                proposal_kind=ProposalKind.HEALING_REVIVAL.value,
                effect=effect.to_payload(),
                step_index=step_index,
                model_instance_id=model_instance_id,
                component_unit_instance_id=component_id,
                source_selection_request_id=source_selection_request_id,
                source_selection_result_id=source_selection_result_id,
            )
        ),
        options=(parameterized_decision_option(),),
    )
    return decisions.request_decision(request)


def healing_effect_from_revival_request(*, request: DecisionRequest) -> HealingEffect:
    payload = _healing_revival_request_payload(request)
    return HealingEffect.from_payload(payload["effect"])


def invalid_healing_revival_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    try:
        _validated_healing_revival_submission(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset_descriptor,
        )
    except (
        DecisionError,
        GameLifecycleError,
        GeometryError,
        PlacementError,
        UnitCoherencyError,
        KeyError,
        TypeError,
    ) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Healing revival placement is invalid.",
            payload={
                "game_id": state.game_id,
                "request_id": request.request_id,
                "result_id": result.result_id,
                "invalid_reason": f"malformed_or_invalid:{type(exc).__name__}",
            },
        )
    return None


def apply_healing_revival_placement_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    result: DecisionResult,
) -> tuple[HealingEffect, DecisionRequest | None]:
    request = decisions.queue.peek_next()
    validated = _validated_healing_revival_submission(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if validated.effect.to_payload() != effect.to_payload():
        raise GameLifecycleError("Healing revival request effect drift.")
    decisions.submit_result(result)
    return apply_recorded_healing_revival_placement_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        request=request,
        result=result,
        effect=effect,
    )


def apply_recorded_healing_revival_placement_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    request: DecisionRequest,
    result: DecisionResult,
    effect: HealingEffect | None = None,
) -> tuple[HealingEffect, DecisionRequest | None]:
    decisions.record_for_result(result)
    validated = _validated_healing_revival_submission(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
    )
    active_effect = validated.effect if effect is None else effect
    if validated.effect.to_payload() != active_effect.to_payload():
        raise GameLifecycleError("Healing revival request effect drift.")
    state.replace_army_definitions(list(validated.hypothetical_armies))
    state.replace_battlefield_state(validated.hypothetical_battlefield)
    step = HealingStep(
        step_index=active_effect.next_step_index(),
        step_kind=HealingStepKind.REVIVE_MODEL,
        model_instance_id=validated.model_instance_id,
        starting_wounds_remaining=validated.starting_wounds_remaining,
        final_wounds_remaining=validated.final_wounds_remaining,
        request_id=request.request_id,
        result_id=result.result_id,
        transition_batch=validated.transition_batch,
    )
    updated = active_effect.with_step(step)
    decisions.event_log.append(
        "healing_step_resolved",
        {
            "effect_id": updated.effect_id,
            "target_unit_instance_id": updated.target_unit_instance_id,
            "amount": updated.amount,
            "source_rule_id": updated.source_rule_id,
            "source_context": updated.source_context,
            "step": validate_json_value(step.to_payload()),
        },
    )
    return resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=updated,
    )


def _validated_healing_revival_submission(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> ValidatedHealingRevival:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Healing revival requires a RulesetDescriptor.")
    payload = _healing_revival_request_payload(request)
    effect = HealingEffect.from_payload(payload["effect"])
    result.validate_for_request(request)
    model_instance_id = payload["model_instance_id"]
    if model_instance_id not in healing_revival_candidate_model_ids(state=state, effect=effect):
        raise GameLifecycleError("Healing revival candidate is stale.")
    if payload["step_index"] != effect.next_step_index():
        raise GameLifecycleError("Healing revival step index drift.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    component_id = rules_unit.component_unit_id_for_model(model_instance_id)
    if payload["component_unit_instance_id"] != component_id:
        raise GameLifecycleError("Healing revival component ownership drift.")
    owner_id = unit_owner_player_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    if result.actor_id != owner_id:
        raise GameLifecycleError("Healing revival actor drift.")
    army = _army_for_component(state=state, component_unit_instance_id=component_id)
    submission = _healing_revival_submission(
        result=result,
    )
    unit_placement = submission.require_unit_placement()
    if submission.proposal_request_id != request.request_id:
        raise GameLifecycleError("Healing revival proposal request is stale.")
    if submission.proposal_kind is not ProposalKind.HEALING_REVIVAL:
        raise GameLifecycleError("Healing revival proposal kind drift.")
    if submission.placement_kind is not BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD:
        raise GameLifecycleError("Healing revival placement kind drift.")
    if submission.unit_instance_id != component_id:
        raise GameLifecycleError("Healing revival unit ownership drift.")
    if unit_placement.army_id != army.army_id or unit_placement.player_id != owner_id:
        raise GameLifecycleError("Healing revival army or player ownership drift.")
    if len(unit_placement.model_placements) != 1:
        raise GameLifecycleError("Healing revival must place exactly one model.")
    placement = unit_placement.model_placements[0]
    if placement.model_instance_id != model_instance_id:
        raise GameLifecycleError("Healing revival model identity drift.")
    if submission.large_model_exceptions or submission.restriction_overrides:
        raise GameLifecycleError("Healing revival does not accept placement exceptions.")
    if (
        submission.transport_unit_instance_id is not None
        or submission.disembark_mode is not None
        or submission.transport_movement_status is not None
    ):
        raise GameLifecycleError("Healing revival does not accept transport context.")
    return _validate_revival_placement(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
        rules_unit=rules_unit,
        placement=placement,
    )


def _healing_revival_request_payload(request: DecisionRequest) -> HealingRevivalRequestPayload:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Healing revival routing requires a DecisionRequest.")
    if request.decision_type != SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Healing revival request decision_type drift.")
    raw = request.payload
    if not isinstance(raw, dict):
        raise GameLifecycleError("Healing revival request payload must be an object.")
    if raw.get("submission_kind") != SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Healing revival request submission_kind drift.")
    if raw.get("proposal_kind") != ProposalKind.HEALING_REVIVAL.value:
        raise GameLifecycleError("Healing revival request proposal_kind drift.")
    effect_payload = raw.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Healing revival request effect must be an object.")
    step_index = raw.get("step_index")
    if type(step_index) is not int:
        raise GameLifecycleError("Healing revival request step_index must be an integer.")
    return HealingRevivalRequestPayload(
        submission_kind=SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
        proposal_kind=ProposalKind.HEALING_REVIVAL.value,
        effect=cast(HealingEffectPayload, effect_payload),
        step_index=step_index,
        model_instance_id=_payload_string(raw, key="model_instance_id"),
        component_unit_instance_id=_payload_string(
            raw,
            key="component_unit_instance_id",
        ),
        source_selection_request_id=_optional_payload_string(
            raw,
            key="source_selection_request_id",
        ),
        source_selection_result_id=_optional_payload_string(
            raw,
            key="source_selection_result_id",
        ),
    )


def _healing_revival_submission(
    *,
    result: DecisionResult,
) -> PlacementProposalPayload:
    raw = result.payload
    if not isinstance(raw, dict):
        raise GameLifecycleError("Healing revival result payload must be an object.")
    return PlacementProposalPayload.from_payload(cast(PlacementProposalPayloadPayload, raw))


def _validate_revival_placement(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    rules_unit: RulesUnitView,
    placement: ModelPlacement,
) -> ValidatedHealingRevival:
    model = model_by_id(state=state, model_instance_id=placement.model_instance_id)
    if model.is_alive:
        raise GameLifecycleError("Only destroyed models can be revived.")
    battlefield = _battlefield_state(state)
    if model.model_instance_id not in set(battlefield.removed_model_ids):
        raise GameLifecycleError("Revived model must be removed from the battlefield.")
    if not effect.phase_start_model_ids:
        raise GameLifecycleError("Revival requires phase-start model anchors.")
    validate_returned_model_endpoints(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        placements=(placement,),
        placement_label="Healing revival placement",
    )
    final_wounds = hctx.revival_wounds_remaining(effect.source_context, model.starting_wounds)
    hypothetical_armies = healing_army_definitions_with_model_wounds(
        armies=tuple(state.army_definitions),
        model_instance_id=model.model_instance_id,
        wounds_remaining=final_wounds,
    )
    hypothetical_battlefield = _battlefield_with_returned_revival_model(
        battlefield=battlefield,
        rules_unit=rules_unit,
        placement=placement,
    )
    scenario = BattlefieldScenario(
        armies=hypothetical_armies,
        battlefield_state=hypothetical_battlefield,
    )
    hypothetical_rules_unit = rules_unit_view_from_armies(
        armies=hypothetical_armies,
        unit_instance_id=effect.target_unit_instance_id,
    )
    coherency = rules_unit_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=hypothetical_rules_unit,
    )
    if not coherency.is_coherent:
        raise GameLifecycleError("Healing revival placement breaks unit coherency.")
    _validate_phase_start_anchor_coherency(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
        rules_unit=hypothetical_rules_unit,
        placement=placement,
    )
    _validate_revived_model_engagement(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
        placement=placement,
    )
    transition = BattlefieldTransitionBatch(
        placements=(
            ModelPlacementRecord(
                model_instance_id=placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
                pose=placement.pose,
                source_phase=None,
                source_step=None,
                source_rule_id=effect.source_rule_id,
                source_event_id=None,
            ),
        )
    )
    return ValidatedHealingRevival(
        effect=effect,
        model_instance_id=model.model_instance_id,
        starting_wounds_remaining=model.wounds_remaining,
        final_wounds_remaining=final_wounds,
        placement=placement,
        hypothetical_armies=hypothetical_armies,
        hypothetical_battlefield=hypothetical_battlefield,
        transition_batch=transition,
    )


def _validate_phase_start_anchor_coherency(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    rules_unit: RulesUnitView,
    placement: ModelPlacement,
) -> None:
    policy = ruleset_descriptor.coherency_policy
    if policy.max_horizontal_inches is None or policy.max_vertical_inches is None:
        raise GameLifecycleError("Revival coherency policy is incomplete.")
    phase_start_ids = set(effect.phase_start_model_ids)
    all_placements = _rules_unit_model_placements(scenario=scenario, rules_unit=rules_unit)
    phase_start_placements = tuple(
        candidate for candidate in all_placements if candidate.model_instance_id in phase_start_ids
    )
    if not phase_start_placements:
        raise GameLifecycleError("Revival has no phase-start model anchors.")
    revived_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(placement),
        placement=placement,
    )
    neighbor_count = 0
    for anchor in phase_start_placements:
        anchor_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(anchor),
            placement=anchor,
        )
        if (
            revived_model.base_distance_to(anchor_model) <= policy.max_horizontal_inches
            and revived_model.volume.vertical_gap_to(
                revived_model.pose,
                anchor_model.volume,
                anchor_model.pose,
            )
            <= policy.max_vertical_inches
        ):
            neighbor_count += 1
    if neighbor_count < _required_neighbor_count(
        ruleset_descriptor=ruleset_descriptor,
        model_count=len(all_placements),
    ):
        raise GameLifecycleError("Revived model is not coherent with phase-start models.")


def _validate_revived_model_engagement(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    placement: ModelPlacement,
) -> None:
    revived_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(placement),
        placement=placement,
    )
    allowed_enemy_ids = set(effect.phase_start_enemy_engagement_model_ids)
    engaged_enemy_ids: set[str] = set()
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == placement.player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            for enemy_placement in unit_placement.model_placements:
                enemy_instance = scenario.model_instance_for_placement(enemy_placement)
                if not enemy_instance.is_alive:
                    continue
                enemy_model = geometry_model_for_placement(
                    model=enemy_instance,
                    placement=enemy_placement,
                )
                if revived_model.is_within_engagement_range(
                    enemy_model,
                    horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                    vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                ):
                    engaged_enemy_ids.add(enemy_placement.model_instance_id)
    if engaged_enemy_ids - allowed_enemy_ids:
        raise GameLifecycleError("Revived model engages a new enemy model.")


def _battlefield_with_returned_revival_model(
    *,
    battlefield: BattlefieldRuntimeState,
    rules_unit: RulesUnitView,
    placement: ModelPlacement,
) -> BattlefieldRuntimeState:
    if battlefield.is_unit_placed(placement.unit_instance_id):
        try:
            return battlefield.with_returned_model_placement(placement)
        except PlacementError as exc:
            raise GameLifecycleError("Revival placement cannot return model.") from exc
    if not rules_unit.is_attached_rules_unit:
        raise GameLifecycleError("Revival placement cannot return model to an unplaced unit.")
    if placement.unit_instance_id not in rules_unit.component_unit_instance_ids:
        raise GameLifecycleError("Revival placement component is not in the attached unit.")
    if not any(
        battlefield.is_unit_placed(component_id)
        for component_id in rules_unit.component_unit_instance_ids
    ):
        raise GameLifecycleError("Revival requires an attached component on the battlefield.")
    return _battlefield_with_returned_model_new_component(
        battlefield=battlefield,
        placement=placement,
    )


def _battlefield_with_returned_model_new_component(
    *,
    battlefield: BattlefieldRuntimeState,
    placement: ModelPlacement,
) -> BattlefieldRuntimeState:
    if placement.model_instance_id not in set(battlefield.removed_model_ids):
        raise GameLifecycleError("Revival placement model is not removed.")
    placed_armies: list[PlacedArmy] = []
    did_place = False
    for placed_army in battlefield.placed_armies:
        if placed_army.army_id != placement.army_id:
            placed_armies.append(placed_army)
            continue
        if placed_army.player_id != placement.player_id:
            raise GameLifecycleError("Revival placement player drift.")
        placed_armies.append(
            PlacedArmy(
                army_id=placed_army.army_id,
                player_id=placed_army.player_id,
                unit_placements=tuple(
                    sorted(
                        (
                            *placed_army.unit_placements,
                            UnitPlacement(
                                army_id=placement.army_id,
                                player_id=placement.player_id,
                                unit_instance_id=placement.unit_instance_id,
                                model_placements=(placement,),
                            ),
                        ),
                        key=lambda unit_placement: unit_placement.unit_instance_id,
                    )
                ),
            )
        )
        did_place = True
    if not did_place:
        raise GameLifecycleError("Revival placement army is not on the battlefield.")
    return BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        terrain_features=battlefield.terrain_features,
        placed_armies=tuple(placed_armies),
        removed_model_ids=tuple(
            sorted(
                model_id
                for model_id in battlefield.removed_model_ids
                if model_id != placement.model_instance_id
            )
        ),
    )


def _rules_unit_model_placements(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    placements: list[ModelPlacement] = []
    for component in rules_unit.components:
        unit_placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if unit_placement is None:
            if not any(model.is_alive for model in component.unit.own_models):
                continue
            raise GameLifecycleError("Living revival component is not on the battlefield.")
        placements.extend(unit_placement.model_placements)
    return tuple(sorted(placements, key=lambda candidate: candidate.model_instance_id))


def _army_for_component(
    *,
    state: GameState,
    component_unit_instance_id: str,
) -> ArmyDefinition:
    for army in state.army_definitions:
        if any(unit.unit_instance_id == component_unit_instance_id for unit in army.units):
            return army
    raise GameLifecycleError("Healing revival component is not in an army.")


def _required_neighbor_count(
    *,
    ruleset_descriptor: RulesetDescriptor,
    model_count: int,
) -> int:
    policy = ruleset_descriptor.coherency_policy
    threshold = policy.large_unit_model_count_threshold
    if threshold is not None and model_count >= threshold:
        if policy.required_neighbors_large_unit is None:
            raise GameLifecycleError("Revival large-unit coherency policy is incomplete.")
        return policy.required_neighbors_large_unit
    if policy.required_neighbors_small_unit is None:
        raise GameLifecycleError("Revival small-unit coherency policy is incomplete.")
    return policy.required_neighbors_small_unit


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Healing revival requires battlefield_state.")
    if type(battlefield) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Healing revival battlefield_state is invalid.")
    return battlefield


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Healing revival {key} must be a non-empty string.")
    return value.strip()


def _optional_payload_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Healing revival {key} must be null or a string.")
    return value.strip()


__all__ = (
    "SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE",
    "apply_healing_revival_placement_decision",
    "apply_recorded_healing_revival_placement_decision",
    "healing_effect_from_revival_request",
    "invalid_healing_revival_placement_status",
    "request_healing_revival_placement",
)
