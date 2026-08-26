from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    ModelPlacementPayload,
    PlacementError,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.model_logical_death import (
    append_damage_application_model_logical_death_event,
    append_direct_rule_model_logical_death_event,
    model_logical_death_event_for_cause_id_or_none,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import DamageApplication
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def attack_damage_model_logical_death_event(
    *,
    state: GameState,
    decisions: DecisionController,
    cause_id: str,
    producer_id: str,
    damage: DamageApplication,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
) -> EventRecord:
    return append_damage_application_model_logical_death_event(
        state=state,
        event_log=decisions.event_log,
        cause_id=cause_id,
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=producer_id,
        model_instance_id=damage.model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        destroyed_model_placement=_current_destroyed_model_placement(
            state=state,
            model_instance_id=damage.model_instance_id,
        ),
        placement_retained=True,
        damage_application=validate_json_value(damage.to_payload()),
    )


def rule_effect_model_logical_death_event(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    cause_id: str,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    source_rule_id: str,
) -> EventRecord:
    existing = model_logical_death_event_for_cause_id_or_none(
        event_records=decisions.event_log.records,
        cause_id=cause_id,
    )
    if existing is not None:
        return existing
    if root_context.get("damage_application") is not None:
        raise GameLifecycleError("Applied rule damage is missing its logical-death boundary.")
    return append_direct_rule_model_logical_death_event(
        state=state,
        event_log=decisions.event_log,
        cause_id=cause_id,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        destroyed_model_placement=_context_model_placement(root_context),
        source_rule_id=source_rule_id,
        source_result_id=producer_id,
    )


def _current_destroyed_model_placement(
    *,
    state: GameState,
    model_instance_id: str,
) -> ModelPlacement:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Model destruction cause reservation requires battlefield state.")
    try:
        return battlefield.model_placement_by_id(model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Model destruction cause reservation requires retained placement."
        ) from exc


def _context_model_placement(root_context: dict[str, JsonValue]) -> ModelPlacement:
    raw = root_context.get("destroyed_model_placement")
    if not isinstance(raw, dict):
        raise GameLifecycleError(
            "Rule destruction cause requires destroyed-model placement evidence."
        )
    try:
        return ModelPlacement.from_payload(cast(ModelPlacementPayload, raw))
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Rule destruction cause placement evidence is invalid.") from exc


__all__ = (
    "attack_damage_model_logical_death_event",
    "rule_effect_model_logical_death_event",
)
