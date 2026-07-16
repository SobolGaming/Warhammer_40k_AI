from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    ModelPlacementPayload,
    PlacedArmy,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


FIGHT_ON_DEATH_AWAITING_EFFECT_KIND = "fight_on_death_awaiting_attack"


def model_is_present_on_battlefield(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    model, _unit = _model_and_unit_by_id(state=state, model_instance_id=requested_model_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Battlefield presence query requires battlefield_state.")
    if battlefield.model_placement_or_none(requested_model_id) is None:
        return False
    return (
        model.is_alive
        or _awaiting_effect_for_model_or_none(
            state=state,
            model_instance_id=requested_model_id,
        )
        is not None
    )


def restore_selected_model_awaiting_fight_on_death(
    *,
    state: GameState,
    decisions: DecisionController,
    model_destroyed_event_id: str,
    model_instance_id: str,
    source_id: str,
    source_rule_id: str,
    source_phase: BattlePhaseKind,
) -> ModelPlacement:
    requested_event_id = _validate_identifier(
        "model_destroyed_event_id",
        model_destroyed_event_id,
    )
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    matching_records = tuple(
        record for record in decisions.event_log.records if record.event_id == requested_event_id
    )
    if len(matching_records) != 1:
        raise GameLifecycleError("Fight On Death requires one model_destroyed event.")
    record = matching_records[0]
    if record.event_type != "model_destroyed":
        raise GameLifecycleError("Fight On Death event type drift.")
    payload = _payload_object(record.payload, field_name="model_destroyed payload")
    placement_payload = _payload_object(
        payload.get("destroyed_model_placement"),
        field_name="destroyed_model_placement",
    )
    placement = ModelPlacement.from_payload(cast(ModelPlacementPayload, placement_payload))
    if placement.model_instance_id != requested_model_id:
        raise GameLifecycleError("Fight On Death destroyed model placement drift.")
    effect_id = f"fight-on-death-awaiting:{requested_event_id}"
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=placement,
        effect_id=effect_id,
        source_rule_id=requested_source_rule_id,
        source_phase=source_phase,
    )
    decisions.event_log.append(
        "fight_on_death_model_awaiting_attack",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": source_phase.value,
            "model_instance_id": placement.model_instance_id,
            "unit_instance_id": placement.unit_instance_id,
            "source_id": requested_source_id,
            "source_rule_id": requested_source_rule_id,
            "effect_id": effect_id,
            "model_placement": placement.to_payload(),
        },
    )
    return placement


def restore_model_awaiting_fight_on_death(
    *,
    state: GameState,
    placement: ModelPlacement,
    effect_id: str,
    source_rule_id: str,
    source_phase: BattlePhaseKind,
) -> None:
    if type(placement) is not ModelPlacement:
        raise GameLifecycleError("Fight On Death restore requires ModelPlacement.")
    requested_effect_id = _validate_identifier("effect_id", effect_id)
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    if type(source_phase) is not BattlePhaseKind:
        raise GameLifecycleError("Fight On Death source_phase must be a BattlePhaseKind.")
    model, unit, army_id, player_id = _model_unit_and_owner_by_id(
        state=state,
        model_instance_id=placement.model_instance_id,
    )
    if model.is_alive:
        raise GameLifecycleError("Fight On Death restore requires a destroyed model.")
    if placement.unit_instance_id != unit.unit_instance_id:
        raise GameLifecycleError("Fight On Death placement unit drift.")
    if placement.army_id != army_id or placement.player_id != player_id:
        raise GameLifecycleError("Fight On Death placement owner drift.")
    if (
        _awaiting_effect_for_model_or_none(
            state=state,
            model_instance_id=model.model_instance_id,
        )
        is not None
    ):
        raise GameLifecycleError("Fight On Death model is already awaiting its attack.")
    if any(effect.effect_id == requested_effect_id for effect in state.persisting_effects):
        raise GameLifecycleError("Fight On Death effect_id is already in use.")
    if state.active_player_id is None:
        raise GameLifecycleError("Fight On Death restore requires active_player_id.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight On Death restore requires battlefield_state.")
    restored = _battlefield_with_restored_model(
        battlefield=battlefield,
        placement=placement,
    )
    effect = PersistingEffect(
        effect_id=requested_effect_id,
        source_rule_id=requested_source_rule_id,
        owner_player_id=player_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=source_phase,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=source_phase,
            player_id=state.active_player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": FIGHT_ON_DEATH_AWAITING_EFFECT_KIND,
                "model_instance_id": model.model_instance_id,
            }
        ),
    )
    state.replace_battlefield_state(restored)
    state.record_persisting_effect(effect)


def remove_models_awaiting_fight_on_death(
    *,
    state: GameState,
    unit_instance_id: str | None = None,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight On Death cleanup requires battlefield_state.")
    target_component_unit_ids: frozenset[str] | None = None
    if unit_instance_id is not None:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        target_component_unit_ids = frozenset(
            component.unit.unit_instance_id
            for component in rules_unit_view_by_id(
                state=state,
                unit_instance_id=requested_unit_id,
            ).components
        )
    effects = tuple(
        effect
        for effect in state.persisting_effects
        if _is_fight_on_death_awaiting_effect(effect)
        and (
            target_component_unit_ids is None
            or bool(target_component_unit_ids.intersection(effect.target_unit_instance_ids))
        )
    )
    if not effects:
        return ()
    model_ids = tuple(sorted(_awaiting_effect_model_id(effect) for effect in effects))
    if len(set(model_ids)) != len(model_ids):
        raise GameLifecycleError("Fight On Death awaiting effects must target unique models.")
    for model_id in model_ids:
        model, _unit = _model_and_unit_by_id(state=state, model_instance_id=model_id)
        if model.is_alive:
            raise GameLifecycleError("Fight On Death awaiting model cannot be alive at cleanup.")
        if battlefield.model_placement_or_none(model_id) is None:
            raise GameLifecycleError("Fight On Death awaiting model placement is missing.")
    state.replace_battlefield_state(battlefield.with_removed_models(model_ids))
    state.remove_persisting_effects_by_id(tuple(effect.effect_id for effect in effects))
    return model_ids


def _battlefield_with_restored_model(
    *,
    battlefield: BattlefieldRuntimeState,
    placement: ModelPlacement,
) -> BattlefieldRuntimeState:
    if battlefield.model_placement_or_none(placement.model_instance_id) is not None:
        raise GameLifecycleError("Fight On Death model is already placed.")
    if placement.model_instance_id not in battlefield.removed_model_ids:
        raise GameLifecycleError("Fight On Death model was not removed from the battlefield.")
    placed_army = next(
        (army for army in battlefield.placed_armies if army.army_id == placement.army_id),
        None,
    )
    if placed_army is not None and placed_army.player_id != placement.player_id:
        raise GameLifecycleError("Fight On Death placed army owner drift.")
    if placed_army is not None and any(
        unit.unit_instance_id == placement.unit_instance_id for unit in placed_army.unit_placements
    ):
        try:
            return battlefield.with_returned_model_placement(placement)
        except PlacementError as exc:
            raise GameLifecycleError("Fight On Death model cannot be restored.") from exc
    restored_unit = UnitPlacement(
        army_id=placement.army_id,
        player_id=placement.player_id,
        unit_instance_id=placement.unit_instance_id,
        model_placements=(placement,),
    )
    placed_armies = tuple(
        sorted(
            (
                *(army for army in battlefield.placed_armies if army.army_id != placement.army_id),
                PlacedArmy(
                    army_id=placement.army_id,
                    player_id=placement.player_id,
                    unit_placements=(
                        (restored_unit,)
                        if placed_army is None
                        else tuple(
                            sorted(
                                (*placed_army.unit_placements, restored_unit),
                                key=lambda unit: unit.unit_instance_id,
                            )
                        )
                    ),
                ),
            ),
            key=lambda army: army.army_id,
        )
    )
    return BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        placed_armies=placed_armies,
        terrain_features=battlefield.terrain_features,
        removed_model_ids=tuple(
            model_id
            for model_id in battlefield.removed_model_ids
            if model_id != placement.model_instance_id
        ),
    )


def _awaiting_effect_for_model_or_none(
    *,
    state: GameState,
    model_instance_id: str,
) -> PersistingEffect | None:
    matching = tuple(
        effect
        for effect in state.persisting_effects
        if _is_fight_on_death_awaiting_effect(effect)
        and _awaiting_effect_model_id(effect) == model_instance_id
    )
    if len(matching) > 1:
        raise GameLifecycleError("Fight On Death model has duplicate awaiting effects.")
    return None if not matching else matching[0]


def _is_fight_on_death_awaiting_effect(effect: PersistingEffect) -> bool:
    payload = effect.effect_payload
    return isinstance(payload, dict) and (
        payload.get("effect_kind") == FIGHT_ON_DEATH_AWAITING_EFFECT_KIND
    )


def _awaiting_effect_model_id(effect: PersistingEffect) -> str:
    payload = _payload_object(effect.effect_payload, field_name="Fight On Death effect_payload")
    if payload.get("effect_kind") != FIGHT_ON_DEATH_AWAITING_EFFECT_KIND:
        raise GameLifecycleError("PersistingEffect is not a Fight On Death awaiting effect.")
    return _validate_identifier(
        "Fight On Death model_instance_id", payload.get("model_instance_id")
    )


def _model_and_unit_by_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[ModelInstance, UnitInstance]:
    model, unit, _army_id, _player_id = _model_unit_and_owner_by_id(
        state=state,
        model_instance_id=model_instance_id,
    )
    return model, unit


def _model_unit_and_owner_by_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[ModelInstance, UnitInstance, str, str]:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model, unit, army.army_id, army.player_id
    raise GameLifecycleError("Fight On Death model_instance_id is unknown.")


def _payload_object(value: JsonValue | None, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
