from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleDuration,
    RuleDurationKind,
    RuleDurationPayload,
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIRError,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTargetSpecPayload,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class _SelectedTargetChargeEffect:
    persisting_effect: PersistingEffect
    selected_target_unit_instance_id: str


def catalog_selected_target_charge_reroll_permission_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    eligible_target_unit_instance_ids: tuple[str, ...],
) -> RerollPermission | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    eligible_ids = frozenset(
        _validate_identifier_tuple(
            "eligible_target_unit_instance_ids",
            eligible_target_unit_instance_ids,
        )
    )
    candidates = tuple(
        context
        for context in _selected_target_charge_effects_for_unit(
            state=state,
            unit_instance_id=unit_instance_id,
        )
        if context.persisting_effect.owner_player_id == requested_player_id
        and context.selected_target_unit_instance_id in eligible_ids
    )
    if len(candidates) > 1:
        raise GameLifecycleError(
            "Multiple selected-target Charge reroll permissions are available."
        )
    if not candidates:
        return None
    return RerollPermission(
        source_id=f"{candidates[0].persisting_effect.effect_id}:charge-reroll",
        timing_window="after_charge_roll",
        owning_player_id=requested_player_id,
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def catalog_selected_target_required_charge_target_unit_instance_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    eligible_target_unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    eligible_ids = frozenset(
        _validate_identifier_tuple(
            "eligible_target_unit_instance_ids",
            eligible_target_unit_instance_ids,
        )
    )
    return tuple(
        sorted(
            {
                context.selected_target_unit_instance_id
                for context in _selected_target_charge_effects_for_unit(
                    state=state,
                    unit_instance_id=unit_instance_id,
                )
                if context.selected_target_unit_instance_id in eligible_ids
            }
        )
    )


def _selected_target_charge_effects_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[_SelectedTargetChargeEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Selected-target Charge effect lookup requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    contexts: list[_SelectedTargetChargeEffect] = []
    for persisting_effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = persisting_effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        rule_effect = _rule_effect_from_payload(payload)
        parameters = parameter_payload(rule_effect.parameters)
        if (
            rule_effect.kind is not RuleEffectKind.REROLL_PERMISSION
            or parameters.get("roll_type") != "charge"
            or parameters.get("target_reference") != "selected_unit"
        ):
            continue
        if (
            frozenset(parameters)
            != frozenset(
                {
                    "must_end_charge_move_engaged_with_selected_unit",
                    "roll_type",
                    "selected_target_unit_instance_id",
                    "target_reference",
                }
            )
            or parameters.get("must_end_charge_move_engaged_with_selected_unit") is not True
        ):
            raise GameLifecycleError("Selected-target Charge effect parameters drifted.")
        selected_target_id = _validate_identifier(
            "selected_target_unit_instance_id",
            parameters.get("selected_target_unit_instance_id"),
        )
        _validate_selected_target_charge_context(
            payload=payload,
            persisting_effect=persisting_effect,
            requested_unit_id=requested_unit_id,
            selected_target_id=selected_target_id,
        )
        contexts.append(
            _SelectedTargetChargeEffect(
                persisting_effect=persisting_effect,
                selected_target_unit_instance_id=selected_target_id,
            )
        )
    return tuple(sorted(contexts, key=lambda context: context.persisting_effect.effect_id))


def _validate_selected_target_charge_context(
    *,
    payload: Mapping[str, JsonValue],
    persisting_effect: PersistingEffect,
    requested_unit_id: str,
    selected_target_id: str,
) -> None:
    target = _rule_target_from_payload(payload)
    duration = _rule_duration_from_payload(payload)
    selected_context = payload.get("catalog_selected_target")
    if not isinstance(selected_context, dict):
        raise GameLifecycleError("Selected-target Charge effect requires selection context.")
    if (
        target.kind is not RuleTargetKind.THIS_UNIT
        or target.parameters
        or duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(duration.parameters) != {"boundary": "end", "endpoint": "turn"}
        or persisting_effect.target_unit_instance_ids != (requested_unit_id,)
        or payload.get("target_unit_instance_ids") != [requested_unit_id]
        or payload.get("source_id") != persisting_effect.source_rule_id
        or selected_context.get("selected_target_unit_instance_id") != selected_target_id
    ):
        raise GameLifecycleError("Selected-target Charge effect context drifted.")


def _rule_effect_from_payload(payload: Mapping[str, JsonValue]) -> RuleEffectSpec:
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires effect payload.")
    try:
        return RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, raw_effect))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge effect payload is invalid.") from exc


def _rule_target_from_payload(payload: Mapping[str, JsonValue]) -> RuleTargetSpec:
    raw_target = payload.get("target")
    if not isinstance(raw_target, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires target payload.")
    try:
        return RuleTargetSpec.from_payload(cast(RuleTargetSpecPayload, raw_target))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge target payload is invalid.") from exc


def _rule_duration_from_payload(payload: Mapping[str, JsonValue]) -> RuleDuration:
    raw_duration = payload.get("duration")
    if not isinstance(raw_duration, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires duration payload.")
    try:
        return RuleDuration.from_payload(cast(RuleDurationPayload, raw_duration))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge duration payload is invalid.") from exc


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(_validate_identifier(field_name, value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
