from __future__ import annotations

from dataclasses import dataclass
from typing import Self, cast

from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND = "source_backed_reroll_permission"


@dataclass(frozen=True, slots=True)
class SourceBackedRerollPermissionContext:
    permission: RerollPermission
    source_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if type(self.permission) is not RerollPermission:
            raise GameLifecycleError("Source-backed reroll context requires permission.")
        object.__setattr__(
            self,
            "source_payload",
            _validate_source_payload(self.source_payload),
        )

    @classmethod
    def from_effect_payload(cls, payload: dict[str, JsonValue]) -> Self:
        return cls(
            permission=_reroll_permission_from_effect_payload(payload),
            source_payload=source_payload_from_reroll_effect_payload(payload),
        )


def source_backed_reroll_permission_effect_payload(
    *,
    target_unit_instance_ids: tuple[str, ...],
    permission: RerollPermission,
    source_payload: JsonValue,
) -> JsonValue:
    if type(permission) is not RerollPermission:
        raise GameLifecycleError("Source-backed reroll effect requires RerollPermission.")
    return validate_json_value(
        {
            "effect_kind": SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
            "target_unit_instance_ids": list(
                _validate_identifier_tuple("target_unit_instance_ids", target_unit_instance_ids)
            ),
            "permission": validate_json_value(permission.to_payload()),
            "source_payload": validate_json_value(source_payload),
        }
    )


def source_backed_reroll_permission_for_unit(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    model_instance_id: str | None = None,
    roll_type: str,
    timing_window: str,
    attack_kind: str | None = None,
    target_unit_instance_id: str | None = None,
) -> RerollPermission | None:
    context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        roll_type=roll_type,
        timing_window=timing_window,
        attack_kind=attack_kind,
        target_unit_instance_id=target_unit_instance_id,
    )
    return None if context is None else context.permission


def source_backed_reroll_permission_context_for_unit(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    model_instance_id: str | None = None,
    roll_type: str,
    timing_window: str,
    attack_kind: str | None = None,
    target_unit_instance_id: str | None = None,
) -> SourceBackedRerollPermissionContext | None:
    return select_source_backed_reroll_permission_context(
        source_backed_reroll_permission_contexts_for_unit(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            model_instance_id=model_instance_id,
            roll_type=roll_type,
            timing_window=timing_window,
            attack_kind=attack_kind,
            target_unit_instance_id=target_unit_instance_id,
        )
    )


def source_backed_reroll_permission_contexts_for_unit(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    model_instance_id: str | None = None,
    roll_type: str,
    timing_window: str,
    attack_kind: str | None = None,
    target_unit_instance_id: str | None = None,
) -> tuple[SourceBackedRerollPermissionContext, ...]:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_reroll_permission_contexts_for_unit,
    )
    from warhammer40k_core.engine.tracked_targets import (
        tracked_target_reroll_permission_contexts_for_unit,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Source-backed reroll lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_model_id = (
        None
        if model_instance_id is None
        else _validate_identifier("model_instance_id", model_instance_id)
    )
    requested_roll_type = _validate_identifier("roll_type", roll_type)
    requested_timing_window = _validate_identifier("timing_window", timing_window)
    requested_attack_kind = (
        None if attack_kind is None else _validate_attack_kind("attack_kind", attack_kind)
    )
    requested_target_unit_id = (
        None
        if target_unit_instance_id is None
        else _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    )
    permissions: list[SourceBackedRerollPermissionContext] = []
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        if effect.owner_player_id != requested_player_id:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
            continue
        permission_context = SourceBackedRerollPermissionContext.from_effect_payload(payload)
        if permission_context.permission.owning_player_id != requested_player_id:
            raise GameLifecycleError("Source-backed reroll owner drift.")
        if permission_context.permission.eligible_roll_type != requested_roll_type:
            continue
        if permission_context.permission.timing_window != requested_timing_window:
            continue
        if not _source_payload_target_matches(
            permission_context.source_payload,
            state=state,
            unit_instance_id=requested_unit_id,
            attack_kind=requested_attack_kind,
            target_unit_instance_id=requested_target_unit_id,
        ):
            continue
        permissions.append(permission_context)
    generic_contexts = generic_rule_reroll_permission_contexts_for_unit(
        state=state,
        player_id=requested_player_id,
        unit_instance_id=requested_unit_id,
        model_instance_id=requested_model_id,
        roll_type=requested_roll_type,
        timing_window=requested_timing_window,
        target_unit_instance_id=requested_target_unit_id,
    )
    for generic_context in generic_contexts:
        permissions.append(
            SourceBackedRerollPermissionContext(
                permission=generic_context.permission,
                source_payload=generic_context.source_payload,
            )
        )
    permissions.extend(
        tracked_target_reroll_permission_contexts_for_unit(
            state=state,
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
            model_instance_id=requested_model_id,
            roll_type=requested_roll_type,
            timing_window=requested_timing_window,
            attack_kind=requested_attack_kind,
            target_unit_instance_id=requested_target_unit_id,
        )
    )
    return tuple(permissions)


def select_source_backed_reroll_permission_context(
    candidates: tuple[SourceBackedRerollPermissionContext, ...],
) -> SourceBackedRerollPermissionContext | None:
    if type(candidates) is not tuple:
        raise GameLifecycleError("Reroll permission candidates must be a tuple.")
    if not candidates:
        return None
    unique_by_source_id: dict[str, SourceBackedRerollPermissionContext] = {}
    for candidate in candidates:
        if type(candidate) is not SourceBackedRerollPermissionContext:
            raise GameLifecycleError("Reroll permission candidates require source contexts.")
        existing = unique_by_source_id.get(candidate.permission.source_id)
        if existing is not None and existing != candidate:
            raise GameLifecycleError("Reroll permission source identity drifted.")
        unique_by_source_id[candidate.permission.source_id] = candidate
    unique = tuple(unique_by_source_id.values())
    first = unique[0].permission
    for candidate in unique[1:]:
        permission = candidate.permission
        if (
            permission.timing_window != first.timing_window
            or permission.owning_player_id != first.owning_player_id
            or permission.eligible_roll_type != first.eligible_roll_type
        ):
            raise GameLifecycleError("Reroll permission candidate request identity drifted.")
    return min(unique, key=_reroll_permission_candidate_sort_key)


def _reroll_permission_candidate_sort_key(
    context: SourceBackedRerollPermissionContext,
) -> tuple[int, int, str, str]:
    permission = context.permission
    if permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL:
        policy_rank = 0
        selection_rank = 0
    else:
        policy_rank = 1
        selections = permission.allowed_component_selections
        if selections is None:
            raise GameLifecycleError("Component reroll permission selections are missing.")
        selection_rank = -len(selections)
    return (
        policy_rank,
        selection_rank,
        permission.source_id,
        canonical_json(context.source_payload),
    )


def source_payload_from_reroll_effect_payload(effect_payload: JsonValue) -> dict[str, JsonValue]:
    payload = _payload_object(effect_payload)
    if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
        raise GameLifecycleError("Source-backed reroll effect_kind drift.")
    source_payload = payload.get("source_payload")
    if not isinstance(source_payload, dict):
        raise GameLifecycleError("Source-backed reroll source_payload must be an object.")
    return source_payload


def _validate_source_payload(payload: object) -> dict[str, JsonValue]:
    validated = validate_json_value(payload)
    if not isinstance(validated, dict):
        raise GameLifecycleError("Source-backed reroll context requires source payload.")
    return validated


def _reroll_permission_from_effect_payload(
    payload: dict[str, JsonValue],
) -> RerollPermission:
    permission_payload = payload.get("permission")
    if not isinstance(permission_payload, dict):
        raise GameLifecycleError("Source-backed reroll permission must be an object.")
    return RerollPermission.from_payload(cast(RerollPermissionPayload, permission_payload))


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Source-backed reroll payload must be an object.")
    return payload


def _source_payload_target_matches(
    source_payload: dict[str, JsonValue],
    *,
    state: object,
    unit_instance_id: str,
    attack_kind: str | None,
    target_unit_instance_id: str | None,
) -> bool:
    conditional_attack_kind = source_payload.get("attack_kind")
    if conditional_attack_kind is not None:
        if type(conditional_attack_kind) is not str or not conditional_attack_kind.strip():
            raise GameLifecycleError("Source-backed reroll attack_kind must be a string.")
        if attack_kind != _validate_attack_kind("attack_kind", conditional_attack_kind):
            return False
    conditional_target = source_payload.get("target_unit_instance_id")
    if conditional_target is not None:
        if type(conditional_target) is not str or not conditional_target.strip():
            raise GameLifecycleError(
                "Source-backed reroll target_unit_instance_id must be a string."
            )
        if target_unit_instance_id != conditional_target:
            return False
    return _source_payload_aura_range_matches(
        source_payload,
        state=state,
        unit_instance_id=unit_instance_id,
    )


def _source_payload_aura_range_matches(
    source_payload: dict[str, JsonValue],
    *,
    state: object,
    unit_instance_id: str,
) -> bool:
    source_unit_id = source_payload.get("aura_source_unit_instance_id")
    range_value = source_payload.get("aura_range_inches")
    if source_unit_id is None and range_value is None:
        return True
    if type(source_unit_id) is not str or not source_unit_id.strip():
        raise GameLifecycleError(
            "Source-backed reroll aura_source_unit_instance_id must be a string."
        )
    if type(range_value) not in {int, float}:
        raise GameLifecycleError("Source-backed reroll aura_range_inches must be positive.")
    range_inches = float(cast(int | float, range_value))
    if range_inches <= 0.0:
        raise GameLifecycleError("Source-backed reroll aura_range_inches must be positive.")
    return _units_within_range(
        state=state,
        source_unit_instance_id=source_unit_id,
        target_unit_instance_id=unit_instance_id,
        range_inches=range_inches,
    )


def _units_within_range(
    *,
    state: object,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
    range_inches: float,
) -> bool:
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldScenario,
        geometry_model_for_placement,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.geometry import shapely_backend

    if type(state) is not GameState:
        raise GameLifecycleError("Source-backed reroll aura lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Source-backed reroll aura lookup requires battlefield_state.")
    requested_source_id = _validate_identifier(
        "aura_source_unit_instance_id",
        source_unit_instance_id,
    )
    requested_target_id = _validate_identifier("unit_instance_id", target_unit_instance_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    source_placement = state.battlefield_state.unit_placement_or_none(requested_source_id)
    target_placement = state.battlefield_state.unit_placement_or_none(requested_target_id)
    if source_placement is None or target_placement is None:
        return False
    source_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in source_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )
    target_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in target_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )
    if not source_models or not target_models:
        return False
    return any(
        shapely_backend.base_footprint_distance(
            source_model.base,
            source_model.pose,
            target_model.base,
            target_model.pose,
        )
        <= range_inches
        for source_model in source_models
        for target_model in target_models
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_attack_kind(field_name: str, value: object) -> str:
    token = _validate_identifier(field_name, value)
    if token not in {"melee", "ranged"}:
        raise GameLifecycleError(f"Source-backed reroll unsupported {field_name}: {token}.")
    return token


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, raw_value)
        if identifier in seen:
            raise GameLifecycleError(f"Source-backed reroll {field_name} must be unique.")
        seen.add(identifier)
        identifiers.append(identifier)
    if not identifiers:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must not be empty.")
    return tuple(identifiers)
