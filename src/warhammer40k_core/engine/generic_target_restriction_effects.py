from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID = (
    "generic_rule_ir:persisted-shooting-target-range-restriction"
)
GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID = (
    "generic_rule_ir:persisted-shooting-target-range-restriction"
)
GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE = (
    "generic_persisted_shooting_target_range"
)


@dataclass(frozen=True, slots=True)
class _TargetRangeRestrictionEffect:
    effect: PersistingEffect
    max_range_inches: float
    payload: dict[str, JsonValue]


def shooting_target_restriction_hook_bindings() -> tuple[ShootingTargetRestrictionHookBinding, ...]:
    return (
        ShootingTargetRestrictionHookBinding(
            hook_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
            source_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID,
            handler=generic_persisted_shooting_target_range_restriction,
        ),
    )


def generic_persisted_shooting_target_range_restriction(
    context: ShootingTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires a shooting target "
            "context."
        )
    effects = _target_range_restriction_effects(context)
    if not effects:
        return None
    attacker_model_id = context.attacker_model_instance_id
    if attacker_model_id is None:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires attacker model."
        )
    for effect_context in effects:
        if _attacker_model_within_target_range(
            context,
            attacker_model_instance_id=attacker_model_id,
            target_unit_instance_id=context.target_unit_instance_id,
            max_range_inches=effect_context.max_range_inches,
        ):
            continue
        return TargetRestriction(
            hook_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
            source_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID,
            violation_code=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE,
            message=(
                "Target can only be selected by attacks from models within "
                f'{_format_inches(effect_context.max_range_inches)}".'
            ),
            replay_payload=_restriction_replay_payload(
                effect_context=effect_context,
                attacker_model_instance_id=attacker_model_id,
                target_unit_instance_id=context.target_unit_instance_id,
            ),
        )
    return None


def _target_range_restriction_effects(
    context: ShootingTargetRestrictionContext,
) -> tuple[_TargetRangeRestrictionEffect, ...]:
    effects: list[_TargetRangeRestrictionEffect] = []
    for effect in context.state.persisting_effects_for_unit(context.target_unit_instance_id):
        payload_value = effect.effect_payload
        if not isinstance(payload_value, dict):
            continue
        payload = payload_value
        if "targeting_max_range_inches" not in payload:
            continue
        if payload.get("effect_kind") != SMOKESCREEN_EFFECT_KIND:
            raise GameLifecycleError(
                "Generic persisted shooting target range restriction requires smokescreen "
                "effect_kind."
            )
        effects.append(
            _TargetRangeRestrictionEffect(
                effect=effect,
                max_range_inches=_targeting_max_range_inches(payload),
                payload=payload,
            )
        )
    return tuple(sorted(effects, key=lambda effect_context: effect_context.effect.effect_id))


def _targeting_max_range_inches(payload: dict[str, JsonValue]) -> float:
    value = payload["targeting_max_range_inches"]
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction max range must be numeric."
        )
    max_range_inches = float(value)
    if max_range_inches <= 0.0:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction max range must be positive."
        )
    return max_range_inches


def _attacker_model_within_target_range(
    context: ShootingTargetRestrictionContext,
    *,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    max_range_inches: float,
) -> bool:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires battlefield state."
        )
    attacker_model = _geometry_model_by_model_id(
        context.state,
        model_instance_id=attacker_model_instance_id,
    )
    try:
        target_placement = battlefield.unit_placement_by_id(target_unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction target unit is not placed."
        ) from exc
    target_models = tuple(
        geometry_model_for_placement(
            model=_model_instance_by_id(context.state, placement.model_instance_id),
            placement=placement,
        )
        for placement in target_placement.model_placements
    )
    return any(
        attacker_model.range_to(target_model) <= max_range_inches for target_model in target_models
    )


def _geometry_model_by_model_id(state: object, *, model_instance_id: str) -> GeometryModel:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction geometry lookup requires "
            "GameState."
        )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction geometry lookup requires "
            "battlefield state."
        )
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    try:
        placement = battlefield.model_placement_by_id(requested_model_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction model is not placed."
        ) from exc
    return geometry_model_for_placement(
        model=_model_instance_by_id(state, requested_model_id),
        placement=placement,
    )


def _model_instance_by_id(state: object, model_instance_id: str) -> ModelInstance:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction model lookup requires GameState."
        )
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model
    raise GameLifecycleError(
        "Generic persisted shooting target range restriction model is unknown."
    )


def _restriction_replay_payload(
    *,
    effect_context: _TargetRangeRestrictionEffect,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
) -> JsonValue:
    payload = effect_context.payload
    return validate_json_value(
        {
            "restriction_kind": "persisted_shooting_target_range",
            "persisting_effect_id": effect_context.effect.effect_id,
            "persisting_effect_source_rule_id": effect_context.effect.source_rule_id,
            "persisting_effect_kind": SMOKESCREEN_EFFECT_KIND,
            "source_effect_kind": _optional_payload_string(payload, "source_effect_kind"),
            "stratagem_id": _optional_payload_string(payload, "stratagem_id"),
            "stratagem_use_id": _optional_payload_string(payload, "stratagem_use_id"),
            "attacker_model_instance_id": attacker_model_instance_id,
            "target_unit_instance_id": target_unit_instance_id,
            "max_range_inches": effect_context.max_range_inches,
        }
    )


def _optional_payload_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(
            f"Generic persisted shooting target range restriction payload {key} must be a string."
        )
    return value


def _format_inches(value: float) -> str:
    return f"{value:g}"


_validate_identifier = IdentifierValidator(GameLifecycleError)
