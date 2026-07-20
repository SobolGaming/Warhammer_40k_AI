from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID = "catalog-ir:conditional-leading-bodyguard-ability-grant"
CONDITIONAL_LEADING_ROLL_REROLL_DESCRIPTOR_ID = "catalog-ir:conditional-leading-roll-reroll"
FACTION_RESOURCE_REFUND_ROLL_DESCRIPTOR_ID = "catalog-ir:faction-resource-refund-roll"


def conditional_granted_ability_effects_for_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    component_unit_instance_id: str,
    ability: str,
) -> tuple[PersistingEffect, ...]:
    _require_game_state(state)
    requested_ability = _required_string("ability", ability)
    effects = tuple(
        effect
        for effect in state.persisting_effects_for_unit(component_unit_instance_id)
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("descriptor_id") == CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID
        and generic_rule_effect_payload_grants_ability(
            effect.effect_payload,
            ability=requested_ability,
        )
        and conditional_leader_grant_effect_applies(
            state=state,
            effect=effect,
            rules_unit_instance_id=rules_unit_instance_id,
        )
    )
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def conditional_granted_ability_effects_for_rules_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    ability: str,
) -> tuple[PersistingEffect, ...]:
    view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_instance_id)
    effects = tuple(
        effect
        for component in view.components
        for effect in conditional_granted_ability_effects_for_unit(
            state=state,
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_instance_id=component.unit.unit_instance_id,
            ability=ability,
        )
    )
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def catalog_granted_stealth_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Catalog granted Stealth requires HitRollModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return 0
    target = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    generic_grant = any(
        isinstance(effect.effect_payload, dict)
        and generic_rule_effect_payload_grants_ability(
            effect.effect_payload,
            ability="stealth",
        )
        for effect in context.state.persisting_effects_for_unit(target.unit_instance_id)
    )
    conditional_grant = conditional_granted_ability_effects_for_rules_unit(
        state=context.state,
        rules_unit_instance_id=target.unit_instance_id,
        ability="stealth",
    )
    return -1 if generic_grant or conditional_grant else 0


def conditional_leader_grant_effect_applies(
    *,
    state: GameState,
    effect: PersistingEffect,
    rules_unit_instance_id: str,
) -> bool:
    _require_game_state(state)
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Conditional leader ability query requires typed inputs.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Conditional leader ability effect payload must be an object.")
    if payload.get("descriptor_id") != CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID:
        return False
    if not _conditional_leading_source_applies(
        state=state,
        effect=effect,
        rules_unit_instance_id=rules_unit_instance_id,
    ):
        return False
    required_bodyguard_keyword = _required_bodyguard_keyword(payload)
    view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_instance_id)
    return any(
        component.role == "bodyguard"
        and any(model.is_alive for model in component.unit.own_models)
        and required_bodyguard_keyword
        in {_canonical_keyword(keyword) for keyword in component.unit.keywords}
        for component in view.components
    )


def conditional_leading_roll_reroll_permission(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    player_id: str,
    rule_roll_type: str,
    eligible_roll_type: str,
    timing_window: str,
) -> RerollPermission | None:
    requested_rule_roll_type = _required_string("rule_roll_type", rule_roll_type)
    requested_eligible_roll_type = _required_string(
        "eligible_roll_type",
        eligible_roll_type,
    )
    requested_player_id = _required_string("player_id", player_id)
    requested_timing_window = _required_string("timing_window", timing_window)
    permissions: list[RerollPermission] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if (
            not isinstance(payload, dict)
            or payload.get("descriptor_id") != CONDITIONAL_LEADING_ROLL_REROLL_DESCRIPTOR_ID
            or effect.owner_player_id != requested_player_id
            or not _conditional_leading_source_applies(
                state=state,
                effect=effect,
                rules_unit_instance_id=rules_unit_instance_id,
            )
        ):
            continue
        if _rule_effect_parameter(payload, key="roll_type") != requested_rule_roll_type:
            continue
        permissions.append(
            RerollPermission(
                source_id=f"{effect.effect_id}:reroll",
                timing_window=requested_timing_window,
                owning_player_id=requested_player_id,
                eligible_roll_type=requested_eligible_roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            )
        )
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple conditional leader reroll permissions are available.")
    return permissions[0] if permissions else None


def conditional_faction_resource_refund_roll_payload(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    player_id: str,
    resource_kind: str,
) -> JsonValue:
    requested_player_id = _required_string("player_id", player_id)
    requested_resource_kind = _required_string("resource_kind", resource_kind)
    descriptors: list[dict[str, JsonValue]] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if (
            not isinstance(payload, dict)
            or payload.get("descriptor_id") != FACTION_RESOURCE_REFUND_ROLL_DESCRIPTOR_ID
            or effect.owner_player_id != requested_player_id
            or not _conditional_leading_source_applies(
                state=state,
                effect=effect,
                rules_unit_instance_id=rules_unit_instance_id,
            )
        ):
            continue
        values = _faction_resource_refund_values(payload)
        if values["resource_kind"] != requested_resource_kind:
            continue
        descriptors.append(
            {
                "descriptor_id": FACTION_RESOURCE_REFUND_ROLL_DESCRIPTOR_ID,
                "source_effect_id": effect.effect_id,
                "source_rule_id": effect.source_rule_id,
                **values,
            }
        )
    if len(descriptors) > 1:
        raise GameLifecycleError("Multiple faction resource refund rolls are available.")
    return None if not descriptors else validate_json_value(descriptors[0])


def conditional_granted_ability_distance_inches(effect: PersistingEffect) -> float:
    if type(effect) is not PersistingEffect or not isinstance(effect.effect_payload, dict):
        raise GameLifecycleError("Conditional ability distance requires a typed effect.")
    distance = _rule_effect_parameter(effect.effect_payload, key="distance_inches")
    if not isinstance(distance, int | float) or type(distance) is bool or distance <= 0:
        raise GameLifecycleError("Conditional Scouts distance must be positive.")
    return float(distance)


def _conditional_leading_source_applies(
    *,
    state: GameState,
    effect: PersistingEffect,
    rules_unit_instance_id: str,
) -> bool:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Conditional leader effect payload must be an object.")
    source_unit_id = _source_unit_instance_id(payload)
    view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_instance_id)
    if not view.is_attached_rules_unit:
        return False
    source_components = tuple(
        component
        for component in view.components
        if component.unit.unit_instance_id == source_unit_id
        and component.role in {"leader", "support"}
        and any(model.is_alive for model in component.unit.own_models)
    )
    if len(source_components) != 1:
        return False
    return any(
        component.role == "bodyguard" and any(model.is_alive for model in component.unit.own_models)
        for component in view.components
    )


def _source_unit_instance_id(payload: dict[str, JsonValue]) -> str:
    context = payload.get("context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Conditional leader ability context is missing.")
    return _required_string("source_unit_instance_id", context.get("source_unit_instance_id"))


def _required_bodyguard_keyword(payload: dict[str, JsonValue]) -> str:
    conditions = payload.get("conditions")
    if not isinstance(conditions, list):
        raise GameLifecycleError("Conditional leader ability conditions are missing.")
    values: list[str] = []
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get("kind") != "keyword_gate":
            continue
        parameters = condition.get("parameters")
        if not isinstance(parameters, list):
            raise GameLifecycleError("Conditional leader ability keyword gate is malformed.")
        gate_subject = None
        required_keyword = None
        for parameter in parameters:
            if not isinstance(parameter, dict):
                raise GameLifecycleError("Conditional leader ability parameter is malformed.")
            if parameter.get("key") == "gate_subject":
                gate_subject = parameter.get("value")
            elif parameter.get("key") == "required_keyword":
                required_keyword = parameter.get("value")
        if gate_subject == "bodyguard_unit":
            values.append(_required_string("required_keyword", required_keyword))
    if len(values) != 1:
        raise GameLifecycleError("Conditional leader ability requires one bodyguard keyword.")
    return _canonical_keyword(values[0])


def _rule_effect_parameter(payload: dict[str, JsonValue], *, key: str) -> JsonValue:
    effect = payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Conditional leader RuleIR effect is missing.")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Conditional leader RuleIR parameters are malformed.")
    values = [
        parameter.get("value")
        for parameter in parameters
        if isinstance(parameter, dict) and parameter.get("key") == key
    ]
    if len(values) != 1:
        raise GameLifecycleError(f"Conditional leader RuleIR requires one {key} parameter.")
    return values[0]


def _faction_resource_refund_values(
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    values = {
        key: _rule_effect_parameter(payload, key=key)
        for key in (
            "amount",
            "operation",
            "resource_kind",
            "roll_expression",
            "success_threshold",
        )
    }
    if values != {
        "amount": 1,
        "operation": "gain",
        "resource_kind": "battle_focus_token",
        "roll_expression": "D6",
        "success_threshold": 3,
    }:
        raise GameLifecycleError("Faction resource refund descriptor payload drift.")
    return values


def _canonical_keyword(value: str) -> str:
    return _required_string("keyword", value).upper().replace("-", " ").replace("_", " ")


def _required_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise GameLifecycleError(f"Conditional leader ability {field_name} is invalid.")
    return value


def _require_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Conditional leader rule runtime requires GameState.")
