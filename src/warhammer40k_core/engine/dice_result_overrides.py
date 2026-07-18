from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponProfile
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_result_override_descriptors import (
    DiceResultOverrideDescriptor,
    dice_result_override_descriptors_for_abilities,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import RulesUnitComponent, rules_unit_view_by_id
from warhammer40k_core.engine.unit_resource_state import (
    spend_unit_resource,
    unit_resource_total,
)
from warhammer40k_core.engine.unit_resources import UnitResourceStatus
from warhammer40k_core.engine.weapon_abilities import (
    devastating_wounds_resolution,
    lethal_hits_applies,
    weapon_ability_value,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.game_state import GameState


DICE_RESULT_OVERRIDE_DECISION_TYPE = "select_dice_result_override"
DECLINE_DICE_RESULT_OVERRIDE_OPTION_ID = "decline"
USE_DICE_RESULT_OVERRIDE_OPTION_ID = "use"
DICE_RESULT_OVERRIDE_EVENT_TYPE = "dice_result_overridden"
UNIT_RESOURCE_SPENT_EVENT_TYPE = "unit_resource_spent"
CRITICAL_HIT_LETHAL_HITS_MARKER_ID = "core:critical-hit:lethal-hits"
CRITICAL_HIT_SUSTAINED_HITS_MARKER_ID = "core:critical-hit:sustained-hits"
CRITICAL_WOUND_DEVASTATING_WOUNDS_MARKER_ID = "core:critical-wound:devastating-wounds"


class CriticalTriggerMarkerPayload(TypedDict):
    marker_id: str
    roll_type: str
    source_kind: str
    execution_supported: bool


class DiceResultOverrideRequestPayload(TypedDict):
    roll_id: str
    roll_type: str
    roll_spec_type: str
    roll_successful: bool
    roll_critical: bool
    roll_state: DiceRollStatePayload
    source_phase: str
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile_id: str
    source_component_unit_instance_id: str
    descriptor_id: str
    source_rule_id: str
    resource_kind: str
    resource_cost: int
    current_count: int
    replacement_value: int
    critical_trigger_markers: list[CriticalTriggerMarkerPayload]
    context_fingerprint: str


@dataclass(frozen=True, slots=True)
class CriticalTriggerMarker:
    marker_id: str
    roll_type: str
    source_kind: str
    execution_supported: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "marker_id",
            _validate_identifier("CriticalTriggerMarker marker_id", self.marker_id),
        )
        if self.roll_type not in {"hit", "wound"}:
            raise GameLifecycleError("CriticalTriggerMarker roll_type is invalid.")
        object.__setattr__(
            self,
            "source_kind",
            _validate_identifier("CriticalTriggerMarker source_kind", self.source_kind),
        )
        if type(self.execution_supported) is not bool:
            raise GameLifecycleError("CriticalTriggerMarker execution_supported must be a boolean.")

    def to_payload(self) -> CriticalTriggerMarkerPayload:
        return {
            "marker_id": self.marker_id,
            "roll_type": self.roll_type,
            "source_kind": self.source_kind,
            "execution_supported": self.execution_supported,
        }


def critical_trigger_markers_for_attack(
    *,
    roll_type: str,
    weapon_profile: WeaponProfile,
    target_keywords: tuple[str, ...],
) -> tuple[CriticalTriggerMarker, ...]:
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("Critical trigger markers require a WeaponProfile.")
    if type(target_keywords) is not tuple:
        raise GameLifecycleError("Critical trigger marker target_keywords must be a tuple.")
    markers: list[CriticalTriggerMarker] = []
    if roll_type == "hit":
        if lethal_hits_applies(weapon_profile, target_keywords=target_keywords):
            markers.append(
                CriticalTriggerMarker(
                    marker_id=CRITICAL_HIT_LETHAL_HITS_MARKER_ID,
                    roll_type="hit",
                    source_kind="weapon_ability",
                    execution_supported=True,
                )
            )
        if (
            weapon_ability_value(
                weapon_profile,
                AbilityKind.SUSTAINED_HITS,
                target_keywords=target_keywords,
            )
            is not None
        ):
            markers.append(
                CriticalTriggerMarker(
                    marker_id=CRITICAL_HIT_SUSTAINED_HITS_MARKER_ID,
                    roll_type="hit",
                    source_kind="weapon_ability",
                    execution_supported=True,
                )
            )
    elif roll_type == "wound":
        if (
            devastating_wounds_resolution(
                weapon_profile,
                target_keywords=target_keywords,
            )
            is not None
        ):
            markers.append(
                CriticalTriggerMarker(
                    marker_id=CRITICAL_WOUND_DEVASTATING_WOUNDS_MARKER_ID,
                    roll_type="wound",
                    source_kind="weapon_ability",
                    execution_supported=True,
                )
            )
    else:
        raise GameLifecycleError("Critical trigger marker roll_type is invalid.")
    return tuple(markers)


def request_dice_result_override_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    roll_type: str,
    roll_successful: bool,
    roll_critical: bool,
    source_phase: str,
    sequence_id: str,
    attack_context_id: str,
    pool_index: int,
    attack_index: int,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    weapon_profile_id: str,
    weapon_profile: WeaponProfile,
    target_keywords: tuple[str, ...],
) -> DecisionRequest | None:
    if roll_state is None or roll_state.result_override is not None:
        return None
    if roll_state.current_total == 6 or roll_critical:
        return None
    markers = critical_trigger_markers_for_attack(
        roll_type=roll_type,
        weapon_profile=weapon_profile,
        target_keywords=target_keywords,
    )
    if roll_successful and not markers:
        return None
    if _dice_result_override_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        attack_context_id=attack_context_id,
    ):
        return None
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=attacking_unit_instance_id,
    )
    attacker_component = rules_unit.component_unit_for_model(attacker_model_instance_id)
    eligible: list[tuple[RulesUnitComponent, DiceResultOverrideDescriptor, int]] = []
    for component in rules_unit.components:
        if not any(model.is_alive for model in component.unit.own_models):
            continue
        for descriptor in dice_result_override_descriptors_for_abilities(
            component.unit.datasheet_abilities
        ):
            if roll_type not in descriptor.roll_types:
                continue
            if any(
                keyword in attacker_component.keywords
                for keyword in descriptor.excluded_model_keywords
            ):
                continue
            current_count = unit_resource_total(
                state=state,
                unit_instance_id=component.unit.unit_instance_id,
                resource_kind=descriptor.resource_kind,
            )
            if current_count < descriptor.resource_cost:
                continue
            eligible.append((component, descriptor, current_count))
    if not eligible:
        return None
    if len(eligible) != 1:
        raise GameLifecycleError(
            "An attack roll must not have multiple eligible dice result override sources."
        )
    component, descriptor, current_count = eligible[0]
    source_unit = component.unit
    context = _request_context(
        roll_state=roll_state,
        roll_type=roll_type,
        roll_successful=roll_successful,
        roll_critical=roll_critical,
        source_phase=source_phase,
        sequence_id=sequence_id,
        attack_context_id=attack_context_id,
        pool_index=pool_index,
        attack_index=attack_index,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        weapon_profile_id=weapon_profile_id,
        source_component_unit_instance_id=source_unit.unit_instance_id,
        descriptor=descriptor,
        current_count=current_count,
        markers=markers,
    )
    context["context_fingerprint"] = _context_fingerprint_without_stored(context)
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=DICE_RESULT_OVERRIDE_DECISION_TYPE,
        actor_id=rules_unit.owner_player_id,
        payload=validate_json_value(context),
        options=(
            DecisionOption(
                option_id=DECLINE_DICE_RESULT_OVERRIDE_OPTION_ID,
                label="Decline Dice Result Override",
                payload={
                    "action": "decline",
                    "context_fingerprint": context["context_fingerprint"],
                },
            ),
            DecisionOption(
                option_id=USE_DICE_RESULT_OVERRIDE_OPTION_ID,
                label="Use Dice Result Override",
                payload={
                    "action": "use",
                    "source_component_unit_instance_id": source_unit.unit_instance_id,
                    "source_rule_id": descriptor.source_rule_id,
                    "context_fingerprint": context["context_fingerprint"],
                },
            ),
        ),
    )


def invalid_dice_result_override_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid = _invalid_finite_override_status(
        state=state,
        request=request,
        result=result,
    )
    if invalid is not None:
        return invalid
    if request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE:
        raise GameLifecycleError("Dice result override validator received another decision type.")
    payload = _request_payload(request)
    if payload["context_fingerprint"] != _context_fingerprint_without_stored(payload):
        return _invalid_status(state, field="context_fingerprint")
    sequence = _active_attack_sequence(state=state, sequence_id=payload["sequence_id"])
    if sequence is None:
        return _invalid_status(state, field="sequence_id")
    pool = sequence.current_pool()
    expected_attack_identity = (
        sequence.attack_context_id(),
        sequence.pool_index,
        sequence.attack_index,
        sequence.attacking_unit_instance_id,
        pool.attacker_model_instance_id,
        pool.target_unit_instance_id,
        pool.weapon_profile_id,
        sequence.source_phase.value,
    )
    request_attack_identity = (
        payload["attack_context_id"],
        payload["pool_index"],
        payload["attack_index"],
        payload["attacking_unit_instance_id"],
        payload["attacker_model_instance_id"],
        payload["target_unit_instance_id"],
        payload["weapon_profile_id"],
        payload["source_phase"],
    )
    if expected_attack_identity != request_attack_identity:
        return _invalid_status(state, field="attack_context")
    latest_state = _latest_roll_state(
        decisions=decisions,
        roll_id=payload["roll_id"],
    )
    request_roll_state = DiceRollState.from_payload(payload["roll_state"])
    if latest_state != request_roll_state or latest_state.result_override is not None:
        return _invalid_status(state, field="roll_state")
    if latest_state.original_result.spec.roll_type != payload["roll_spec_type"]:
        return _invalid_status(state, field="roll_spec_type")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=payload["attacking_unit_instance_id"],
    )
    if request.actor_id != rules_unit.owner_player_id:
        return _invalid_status(state, field="actor_id")
    if payload["source_component_unit_instance_id"] not in (rules_unit.component_unit_instance_ids):
        return _invalid_status(state, field="source_component_unit_instance_id")
    source_component = next(
        component.unit
        for component in rules_unit.components
        if component.unit.unit_instance_id == payload["source_component_unit_instance_id"]
    )
    if not any(model.is_alive for model in source_component.own_models):
        return _invalid_status(state, field="source_component_alive")
    attacker_component = rules_unit.component_unit_for_model(payload["attacker_model_instance_id"])
    descriptors = tuple(
        descriptor
        for descriptor in dice_result_override_descriptors_for_abilities(
            source_component.datasheet_abilities
        )
        if descriptor.descriptor_id == payload["descriptor_id"]
    )
    if len(descriptors) != 1:
        return _invalid_status(state, field="descriptor_id")
    descriptor = descriptors[0]
    if (
        descriptor.source_rule_id != payload["source_rule_id"]
        or descriptor.resource_kind != payload["resource_kind"]
        or descriptor.resource_cost != payload["resource_cost"]
        or descriptor.replacement_value != payload["replacement_value"]
        or payload["roll_type"] not in descriptor.roll_types
        or any(
            keyword in attacker_component.keywords for keyword in descriptor.excluded_model_keywords
        )
    ):
        return _invalid_status(state, field="descriptor_context")
    current_count = unit_resource_total(
        state=state,
        unit_instance_id=source_component.unit_instance_id,
        resource_kind=descriptor.resource_kind,
    )
    if current_count != payload["current_count"] or current_count < descriptor.resource_cost:
        return _invalid_status(state, field="current_count")
    target_keywords = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    ).keywords
    expected_markers = [
        marker.to_payload()
        for marker in critical_trigger_markers_for_attack(
            roll_type=payload["roll_type"],
            weapon_profile=pool.weapon_profile,
            target_keywords=target_keywords,
        )
    ]
    if payload["critical_trigger_markers"] != expected_markers:
        return _invalid_status(state, field="critical_trigger_markers")
    return None


def apply_dice_result_override_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    if request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE:
        raise GameLifecycleError("Dice result override applier received another decision type.")
    payload = _request_payload(request)
    if result.selected_option_id == DECLINE_DICE_RESULT_OVERRIDE_OPTION_ID:
        decisions.event_log.append(
            "dice_result_override_declined",
            {
                "request_id": request.request_id,
                "result_id": result.result_id,
                "roll_id": payload["roll_id"],
                "attack_context_id": payload["attack_context_id"],
                "source_rule_id": payload["source_rule_id"],
            },
        )
        return
    if result.selected_option_id != USE_DICE_RESULT_OVERRIDE_OPTION_ID:
        raise GameLifecycleError("Dice result override selected option is invalid.")
    roll_state = DiceRollState.from_payload(payload["roll_state"])
    updated_roll_state = roll_state.with_result_override(
        decision_id=result.result_id,
        request_id=request.request_id,
        source_rule_id=payload["source_rule_id"],
        replacement_value=payload["replacement_value"],
    )
    override_record = updated_roll_state.result_override
    if override_record is None:
        raise GameLifecycleError("Dice result override did not produce an override record.")
    resource_result = spend_unit_resource(
        state=state,
        player_id=cast(str, request.actor_id),
        unit_instance_id=payload["source_component_unit_instance_id"],
        resource_kind=payload["resource_kind"],
        amount=payload["resource_cost"],
        source_rule_id=payload["source_rule_id"],
        decision_request_id=request.request_id,
        decision_result_id=result.result_id,
    )
    if resource_result.status is not UnitResourceStatus.APPLIED:
        raise GameLifecycleError("Validated dice result override resource spend was rejected.")
    decisions.event_log.append(UNIT_RESOURCE_SPENT_EVENT_TYPE, resource_result.to_payload())
    decisions.event_log.append(
        DICE_RESULT_OVERRIDE_EVENT_TYPE,
        {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "roll_id": payload["roll_id"],
            "roll_type": payload["roll_type"],
            "attack_context_id": payload["attack_context_id"],
            "attacker_model_instance_id": payload["attacker_model_instance_id"],
            "source_component_unit_instance_id": payload["source_component_unit_instance_id"],
            "source_rule_id": payload["source_rule_id"],
            "critical_trigger_markers": payload["critical_trigger_markers"],
            "override_record": override_record.to_payload(),
            "updated_roll_state": updated_roll_state.to_payload(),
        },
    )


def _request_context(
    *,
    roll_state: DiceRollState,
    roll_type: str,
    roll_successful: bool,
    roll_critical: bool,
    source_phase: str,
    sequence_id: str,
    attack_context_id: str,
    pool_index: int,
    attack_index: int,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    weapon_profile_id: str,
    source_component_unit_instance_id: str,
    descriptor: DiceResultOverrideDescriptor,
    current_count: int,
    markers: tuple[CriticalTriggerMarker, ...],
) -> DiceResultOverrideRequestPayload:
    return {
        "roll_id": roll_state.original_result.roll_id,
        "roll_type": roll_type,
        "roll_spec_type": roll_state.original_result.spec.roll_type,
        "roll_successful": roll_successful,
        "roll_critical": roll_critical,
        "roll_state": roll_state.to_payload(),
        "source_phase": source_phase,
        "sequence_id": sequence_id,
        "attack_context_id": attack_context_id,
        "pool_index": pool_index,
        "attack_index": attack_index,
        "attacking_unit_instance_id": attacking_unit_instance_id,
        "attacker_model_instance_id": attacker_model_instance_id,
        "target_unit_instance_id": target_unit_instance_id,
        "weapon_profile_id": weapon_profile_id,
        "source_component_unit_instance_id": source_component_unit_instance_id,
        "descriptor_id": descriptor.descriptor_id,
        "source_rule_id": descriptor.source_rule_id,
        "resource_kind": descriptor.resource_kind,
        "resource_cost": descriptor.resource_cost,
        "current_count": current_count,
        "replacement_value": descriptor.replacement_value,
        "critical_trigger_markers": [marker.to_payload() for marker in markers],
        "context_fingerprint": "",
    }


def _request_payload(request: DecisionRequest) -> DiceResultOverrideRequestPayload:
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Dice result override request payload must be an object.")
    return cast(DiceResultOverrideRequestPayload, request.payload)


def _context_fingerprint_without_stored(context: DiceResultOverrideRequestPayload) -> str:
    boundary = cast(dict[str, JsonValue], dict(context))
    boundary.pop("context_fingerprint", None)
    return sha256(canonical_json(boundary).encode("utf-8")).hexdigest()


def _dice_result_override_already_answered(
    *,
    decisions: DecisionController,
    roll_id: str,
    attack_context_id: str,
) -> bool:
    for record in decisions.records:
        if record.request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE:
            continue
        if not isinstance(record.request.payload, dict):
            raise GameLifecycleError("Recorded dice result override payload must be an object.")
        if (
            record.request.payload.get("roll_id") == roll_id
            and record.request.payload.get("attack_context_id") == attack_context_id
        ):
            return True
    return False


def _active_attack_sequence(*, state: GameState, sequence_id: str) -> AttackSequence | None:
    candidates: list[AttackSequence | None] = []
    if state.shooting_phase_state is not None:
        candidates.append(state.shooting_phase_state.attack_sequence)
    if state.out_of_phase_shooting_state is not None:
        candidates.append(state.out_of_phase_shooting_state.attack_sequence)
    if state.fight_phase_state is not None:
        candidates.append(state.fight_phase_state.attack_sequence)
    matching = tuple(
        sequence
        for sequence in candidates
        if sequence is not None and sequence.sequence_id == sequence_id
    )
    if len(matching) > 1:
        raise GameLifecycleError("Active dice result override sequence identity is ambiguous.")
    return None if not matching else matching[0]


def _latest_roll_state(*, decisions: DecisionController, roll_id: str) -> DiceRollState:
    current: DiceRollState | None = None
    for event in decisions.event_log.records:
        if event.event_type == "dice_rolled":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("dice_rolled event payload must be an object.")
            result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
            if result.roll_id == roll_id:
                current = DiceRollState.from_result(result)
            continue
        if event.event_type == "dice_reroll_resolved":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("dice_reroll_resolved payload must be an object.")
            updated = DiceRollState.from_payload(cast(DiceRollStatePayload, event.payload))
        elif event.event_type in {"command_reroll_resolved", DICE_RESULT_OVERRIDE_EVENT_TYPE}:
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Dice roll update event payload must be an object.")
            updated_payload = event.payload.get("updated_roll_state")
            if not isinstance(updated_payload, dict):
                raise GameLifecycleError("Dice roll update event missing updated_roll_state.")
            updated = DiceRollState.from_payload(cast(DiceRollStatePayload, updated_payload))
        else:
            continue
        if updated.original_result.roll_id == roll_id:
            current = updated
    if current is None:
        raise GameLifecycleError("Dice result override roll_id has no event-backed state.")
    return current


def _invalid_status(state: GameState, *, field: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Dice result override context is stale or invalid.",
        payload={
            "invalid_reason": "invalid_dice_result_override_context",
            "field": field,
        },
    )


def _invalid_finite_override_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    field: str | None = None
    if result.request_id != request.request_id:
        field = "request_id"
    elif result.decision_type != request.decision_type:
        field = "decision_type"
    elif result.actor_id != request.actor_id:
        field = "actor_id"
    elif result.selected_option_id not in {option.option_id for option in request.options}:
        field = "selected_option_id"
    else:
        selected_payload = next(
            option.payload
            for option in request.options
            if option.option_id == result.selected_option_id
        )
        if result.payload != selected_payload:
            field = "payload"
    if field is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Dice result override result does not match the pending request.",
        payload={
            "invalid_reason": "invalid_dice_result_override_result",
            "field": field,
        },
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
