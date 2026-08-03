from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence_model import (
    deadly_demise_mortal_wounds_roll_spec,
    deadly_demise_trigger_roll_spec,
)
from warhammer40k_core.engine.battlefield_state import PlacementError, geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    model_by_id,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_views_from_armies
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_deadly_demise_trigger(
    *,
    manager: DiceRollManager,
    source: DestructionReactionSource,
    player_id: str,
    model_instance_id: str,
) -> tuple[dict[str, JsonValue], JsonValue, bool]:
    descriptor = deadly_demise_descriptor(source)
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    roll = manager.roll(
        deadly_demise_trigger_roll_spec(
            source=source,
            player_id=requested_player_id,
            model_instance_id=requested_model_id,
        )
    )
    threshold = _payload_positive_int(descriptor, key="trigger_roll_threshold")
    return descriptor, validate_json_value(roll.to_payload()), roll.current_total >= threshold


def deadly_demise_mortal_wounds_for_target(
    *,
    manager: DiceRollManager,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    player_id: str,
    target_unit_instance_id: str,
) -> tuple[int, JsonValue]:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    wound_descriptor = _payload_object(descriptor.get("mortal_wounds"), "mortal_wounds")
    kind = _payload_string(wound_descriptor, key="kind")
    if kind == "fixed":
        return _payload_positive_int(wound_descriptor, key="value"), None
    if kind == "d3":
        result = manager.roll_d3(
            reason=f"Deadly Demise mortal wounds for {source.source_id} into {requested_target_id}",
            roll_type="destruction_reaction.deadly_demise.mortal_wounds",
            actor_id=requested_player_id,
        )
        return result.value, validate_json_value(result.to_payload())
    if kind == "d6":
        roll = manager.roll(
            deadly_demise_mortal_wounds_roll_spec(
                source=source,
                player_id=requested_player_id,
                target_unit_instance_id=requested_target_id,
                sides=6,
            )
        )
        return roll.current_total, validate_json_value(roll.to_payload())
    raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")


def deadly_demise_target_unit_ids(
    *,
    state: GameState,
    source_model_instance_id: str,
    range_inches: float,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    source_model_id = _validate_identifier("source_model_instance_id", source_model_instance_id)
    requested_range = _validate_positive_number("range_inches", range_inches)
    try:
        source_placement = battlefield.model_placement_by_id(source_model_id)
    except PlacementError as exc:
        raise GameLifecycleError("Deadly Demise source model must remain placed.") from exc
    source_model = geometry_model_for_placement(
        model=model_by_id(state=state, model_instance_id=source_model_id),
        placement=source_placement,
    )
    placed_model_ids = set(battlefield.placed_model_ids())
    target_unit_ids = tuple(
        rules_unit.unit_instance_id
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if _rules_unit_has_model_within_deadly_demise_range(
            state=state,
            rules_unit=rules_unit,
            source_model_id=source_model_id,
            source_model=source_model,
            placed_model_ids=placed_model_ids,
            range_inches=requested_range,
        )
    )
    return tuple(sorted(target_unit_ids))


def deadly_demise_descriptor(
    source: DestructionReactionSource,
) -> dict[str, JsonValue]:
    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
        raise GameLifecycleError("Deadly Demise descriptor requires a Deadly Demise source.")
    payload = _payload_object(source.payload, "Deadly Demise payload")
    range_inches = _validate_positive_number("range_inches", payload.get("range_inches"))
    trigger_threshold = _payload_positive_int(payload, key="trigger_roll_threshold")
    if trigger_threshold > 6:
        raise GameLifecycleError("Deadly Demise trigger_roll_threshold must be on a D6.")
    mortal_wounds = _payload_object(payload.get("mortal_wounds"), "mortal_wounds")
    kind = _payload_string(mortal_wounds, key="kind")
    if kind == "fixed":
        _payload_positive_int(mortal_wounds, key="value")
    elif kind not in {"d3", "d6"}:
        raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")
    return {
        "trigger_roll_threshold": trigger_threshold,
        "range_inches": range_inches,
        "mortal_wounds": validate_json_value(mortal_wounds),
    }


def _rules_unit_has_model_within_deadly_demise_range(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    source_model_id: str,
    source_model: GeometryModel,
    placed_model_ids: set[str],
    range_inches: float,
) -> bool:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    for model in rules_unit.own_models:
        if model.model_instance_id == source_model_id:
            continue
        if not model.is_alive or model.model_instance_id not in placed_model_ids:
            continue
        try:
            placement = battlefield.model_placement_by_id(model.model_instance_id)
        except PlacementError as exc:
            raise GameLifecycleError("Deadly Demise target model placement drift.") from exc
        target_model = geometry_model_for_placement(model=model, placement=placement)
        distance = DistanceMeasurementContext.from_models(source_model, target_model)
        if distance.closest_distance_inches() <= range_inches:
            return True
    return False


def _payload_object(value: JsonValue | None, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Deadly Demise {key} must be a string.")
    return value


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Deadly Demise {key} must be a positive integer.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise GameLifecycleError(f"Deadly Demise {field_name} must be positive.")
    return float(value)


_validate_identifier = IdentifierValidator(GameLifecycleError)
