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
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_identities_share_lineage,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


FIGHT_ON_DEATH_AWAITING_EFFECT_KIND = "fight_on_death_awaiting_attack"


def fight_on_death_model_ids_awaiting_attack(*, state: GameState) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight On Death presence snapshot requires battlefield_state.")
    effects = tuple(
        sorted(
            (
                effect
                for effect in state.persisting_effects
                if _is_fight_on_death_awaiting_effect(effect)
            ),
            key=lambda effect: effect.effect_id,
        )
    )
    model_ids = tuple(sorted(_awaiting_effect_model_id(effect) for effect in effects))
    if len(set(model_ids)) != len(model_ids):
        raise GameLifecycleError("Fight On Death model has duplicate awaiting effects.")
    for effect in effects:
        _validate_awaiting_effect(state=state, battlefield=battlefield, effect=effect)
    return model_ids


def _validate_awaiting_effect(
    *,
    state: GameState,
    battlefield: BattlefieldRuntimeState,
    effect: PersistingEffect,
) -> None:
    model_id = _awaiting_effect_model_id(effect)
    model, unit, _army_id, player_id = _model_unit_and_owner_by_id(
        state=state,
        model_instance_id=model_id,
    )
    if model.is_alive:
        raise GameLifecycleError("Fight On Death awaiting model cannot be alive.")
    if battlefield.model_placement_or_none(model_id) is None:
        raise GameLifecycleError("Fight On Death awaiting model placement is missing.")
    if effect.owner_player_id != player_id:
        raise GameLifecycleError("Fight On Death awaiting effect owner drift.")
    if effect.target_unit_instance_ids != (unit.unit_instance_id,):
        raise GameLifecycleError("Fight On Death awaiting effect target unit drift.")
    if (
        effect.started_battle_round != state.battle_round
        or effect.started_phase is None
        or state.current_battle_phase is None
        or state.current_battle_phase.value != effect.started_phase.value
        or effect.expiration.expiration_kind is not EffectExpirationKind.END_PHASE
        or effect.expiration.battle_round != effect.started_battle_round
        or effect.expiration.phase is not effect.started_phase
        or effect.expiration.player_id != state.active_player_id
    ):
        raise GameLifecycleError("Fight On Death awaiting effect timing drift.")
    payload = _payload_object(
        effect.effect_payload,
        field_name="Fight On Death effect_payload",
    )
    expected_keys = {"effect_kind", "model_instance_id"}
    context = payload.get("completion_context")
    activation_result_id = payload.get("activation_result_id")
    if context is None and activation_result_id is None:
        if set(payload) != expected_keys:
            raise GameLifecycleError("Fight On Death awaiting effect payload fields drift.")
        return
    if not isinstance(context, dict):
        raise GameLifecycleError("Fight On Death completion context is invalid.")
    _validate_identifier("Fight On Death activation_result_id", activation_result_id)
    if set(payload) != {*expected_keys, "activation_result_id", "completion_context"}:
        raise GameLifecycleError("Fight On Death awaiting effect payload fields drift.")
    if context.get("model_instance_id") != model_id:
        raise GameLifecycleError("Fight On Death completion model identity drift.")
    if context.get("destroyed_model_controller_player_id") != player_id:
        raise GameLifecycleError("Fight On Death completion controller drift.")
    _validate_identifier(
        "Fight On Death model_destroyed_event_id",
        context.get("model_destroyed_event_id"),
    )
    context_target_id = _validate_identifier(
        "Fight On Death target_unit_instance_id",
        context.get("target_unit_instance_id"),
    )
    if not rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=context_target_id,
        second_unit_instance_id=unit.unit_instance_id,
    ):
        raise GameLifecycleError("Fight On Death completion rules-unit identity drift.")
    phase = context.get("source_phase", context.get("phase"))
    if phase != effect.started_phase.value:
        raise GameLifecycleError("Fight On Death completion phase drift.")


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
    activation_result_id: str | None = None,
    completion_context: JsonValue = None,
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
        activation_result_id=activation_result_id,
        completion_context=completion_context,
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
    activation_result_id: str | None = None,
    completion_context: JsonValue = None,
) -> None:
    if type(placement) is not ModelPlacement:
        raise GameLifecycleError("Fight On Death restore requires ModelPlacement.")
    requested_effect_id = _validate_identifier("effect_id", effect_id)
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_activation_result_id = (
        None
        if activation_result_id is None
        else _validate_identifier("activation_result_id", activation_result_id)
    )
    validated_completion_context = validate_json_value(completion_context)
    if (requested_activation_result_id is None) != (validated_completion_context is None):
        raise GameLifecycleError(
            "Fight On Death activation_result_id and completion_context must be provided together."
        )
    if validated_completion_context is not None and not isinstance(
        validated_completion_context, dict
    ):
        raise GameLifecycleError("Fight On Death completion_context must be an object.")
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
                **(
                    {}
                    if requested_activation_result_id is None
                    else {
                        "activation_result_id": requested_activation_result_id,
                        "completion_context": validated_completion_context,
                    }
                ),
            }
        ),
    )
    state.replace_battlefield_state(restored)
    state.record_persisting_effect(effect)


def fight_on_death_model_ids_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _awaiting_effect_model_id(effect)
            for effect in _awaiting_effects_for_rules_unit(
                state=state,
                unit_instance_id=unit_instance_id,
            )
        )
    )


def fight_on_death_completion_contexts_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[dict[str, JsonValue], ...]:
    contexts: list[dict[str, JsonValue]] = []
    for effect in _awaiting_effects_for_rules_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    ):
        payload = _payload_object(
            effect.effect_payload,
            field_name="Fight On Death effect_payload",
        )
        context = payload.get("completion_context")
        if context is None:
            if payload.get("activation_result_id") is not None:
                raise GameLifecycleError("Fight On Death completion context is missing.")
            continue
        if not isinstance(context, dict):
            raise GameLifecycleError("Fight On Death completion context is invalid.")
        _validate_identifier(
            "Fight On Death activation_result_id",
            payload.get("activation_result_id"),
        )
        contexts.append(context)
    return tuple(contexts)


def fight_on_death_pending_rule_source_effect_ids(*, state: GameState) -> tuple[str, ...]:
    source_effect_ids: set[str] = set()
    for effect in state.persisting_effects:
        if not _is_fight_on_death_awaiting_effect(effect):
            continue
        payload = _payload_object(
            effect.effect_payload,
            field_name="Fight On Death effect_payload",
        )
        context = payload.get("completion_context")
        if context is None:
            continue
        if not isinstance(context, dict):
            raise GameLifecycleError("Fight On Death completion context is invalid.")
        values = context.get("source_effect_ids")
        if values is None:
            continue
        if not isinstance(values, list) or not all(type(value) is str for value in values):
            raise GameLifecycleError("Rule Fight On Death source_effect_ids are invalid.")
        validated = tuple(
            _validate_identifier("Rule Fight On Death source_effect_id", value) for value in values
        )
        if len(validated) != len(set(validated)):
            raise GameLifecycleError("Rule Fight On Death source_effect_ids are duplicated.")
        source_effect_ids.update(validated)
    return tuple(sorted(source_effect_ids))


def fight_on_death_completion_contexts_for_activation(
    *,
    state: GameState,
    activation_result_id: str,
) -> tuple[dict[str, JsonValue], ...]:
    requested_result_id = _validate_identifier("activation_result_id", activation_result_id)
    matching = tuple(
        effect
        for effect in state.persisting_effects
        if _is_fight_on_death_awaiting_effect(effect)
        and _awaiting_effect_activation_result_id(effect) == requested_result_id
    )
    if not matching:
        return ()
    contexts: list[dict[str, JsonValue]] = []
    for effect in sorted(matching, key=lambda item: item.effect_id):
        payload = _payload_object(
            effect.effect_payload,
            field_name="Fight On Death effect_payload",
        )
        context = payload.get("completion_context")
        if not isinstance(context, dict):
            raise GameLifecycleError("Fight On Death completion context is invalid.")
        contexts.append(context)
    return tuple(contexts)


def remove_models_awaiting_fight_on_death(
    *,
    state: GameState,
    unit_instance_id: str | None = None,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight On Death cleanup requires battlefield_state.")
    effects = (
        tuple(
            effect
            for effect in state.persisting_effects
            if _is_fight_on_death_awaiting_effect(effect)
        )
        if unit_instance_id is None
        else _awaiting_effects_for_rules_unit(
            state=state,
            unit_instance_id=unit_instance_id,
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


def _awaiting_effects_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    view = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    component_unit_ids = frozenset(view.component_unit_instance_ids)
    effects = tuple(
        effect
        for effect in state.persisting_effects
        if _is_fight_on_death_awaiting_effect(effect)
        and bool(component_unit_ids.intersection(effect.target_unit_instance_ids))
    )
    for effect in effects:
        model_id = _awaiting_effect_model_id(effect)
        physical_unit_id = state.unit_instance_id_for_model(model_id)
        if effect.target_unit_instance_ids != (physical_unit_id,):
            raise GameLifecycleError("Fight On Death awaiting effect target unit drift.")
        if physical_unit_id not in component_unit_ids:
            raise GameLifecycleError("Fight On Death awaiting model rules-unit drift.")
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


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


def _awaiting_effect_activation_result_id(effect: PersistingEffect) -> str | None:
    payload = _payload_object(effect.effect_payload, field_name="Fight On Death effect_payload")
    if payload.get("effect_kind") != FIGHT_ON_DEATH_AWAITING_EFFECT_KIND:
        raise GameLifecycleError("PersistingEffect is not a Fight On Death awaiting effect.")
    value = payload.get("activation_result_id")
    if value is None:
        return None
    return _validate_identifier("Fight On Death activation_result_id", value)


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
