"""Engine-owned, occurrence-scoped evaluation of source-linked profile dice."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_random_profiles_2026_09 as random_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

EVALUATION_EVENT_TYPE = "random_profile_values_evaluated"


def has_random_profile_characteristics(
    *, state: GameState, characteristics: tuple[Characteristic, ...]
) -> bool:
    """Inspect source descriptors without constructing physical rules-unit views."""
    return any(
        isinstance(value, RandomProfileValue) and value.characteristic in characteristics
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        for value in model.characteristics
    )


def evaluate_unit_profile_characteristics(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    scope_id: str,
    characteristics: tuple[Characteristic, ...],
    model_instance_ids: tuple[str, ...] | None = None,
    dice_manager: DiceRollManager | None = None,
) -> None:
    """Roll at a rule boundary, atomically replace models, and retain exact evidence.

    Equal M expressions share one independent roll in this rules unit. Every
    other characteristic is evaluated separately for each present model. Re-entry
    into this same engine occurrence consumes no additional dice.
    """
    if type(scope_id) is not str or not scope_id.strip():
        raise GameLifecycleError("Random profile evaluation requires an occurrence identity.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if model_instance_ids is None:
        models = unit.alive_models()
    else:
        selected_ids = frozenset(model_instance_ids)
        models = tuple(m for m in unit.own_models if m.model_instance_id in selected_ids)
        if len(models) != len(model_instance_ids):
            raise GameLifecycleError("Random profile model ownership or identity drifted.")
    evaluated_models = evaluate_model_profile_inventory(
        state=state,
        decisions=decisions,
        models=models,
        unit_instance_id=unit.unit_instance_id,
        player_id=unit.owner_player_id,
        scope_id=scope_id,
        characteristics=characteristics,
        dice_manager=dice_manager,
    )
    if evaluated_models == models:
        return
    replacements = {model.model_instance_id: model for model in evaluated_models}
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        component,
                        own_models=tuple(
                            replacements.get(model.model_instance_id, model)
                            for model in component.own_models
                        ),
                    )
                    if any(
                        model.model_instance_id in replacements for model in component.own_models
                    )
                    else component
                    for component in army.units
                ),
            )
            if army.player_id == unit.owner_player_id
            else army
            for army in state.army_definitions
        ]
    )


def evaluate_model_profile_inventory(
    *,
    state: GameState,
    decisions: DecisionController,
    models: tuple[ModelInstance, ...],
    unit_instance_id: str,
    player_id: str,
    scope_id: str,
    characteristics: tuple[Characteristic, ...],
    dice_manager: DiceRollManager | None = None,
    initialize_wounds: bool = False,
) -> tuple[ModelInstance, ...]:
    """Evaluate an engine-selected inventory, including pre-registration Wounds."""
    if initialize_wounds and (
        characteristics != (Characteristic.WOUNDS,)
        or any(
            isinstance(model.characteristic(Characteristic.WOUNDS), RandomProfileValue)
            and (model.starting_wounds is not None or model.wounds_remaining is not None)
            for model in models
        )
    ):
        raise GameLifecycleError("Random Wounds initialization requires uninitialized models.")
    pending: list[tuple[ModelInstance, RandomProfileValue, str]] = []
    for model in models:
        for value in model.characteristics:
            if (
                not isinstance(value, RandomProfileValue)
                or value.characteristic not in characteristics
            ):
                continue
            evaluation_id = (
                f"{scope_id}:{unit_instance_id}:"
                f"{model.model_instance_id}:{value.characteristic.value}"
            )
            if value.evaluation_id != evaluation_id:
                pending.append((model, value, evaluation_id))
    if not pending:
        return models
    historical: dict[str, dict[str, JsonValue]] = {}
    for event in decisions.event_log.records:
        if event.event_type != EVALUATION_EVENT_TYPE or not isinstance(event.payload, dict):
            continue
        if (
            event.payload.get("scope_id") != scope_id
            or event.payload.get("unit_instance_id") != unit_instance_id
        ):
            continue
        rows = event.payload.get("entries")
        if not isinstance(rows, list):
            raise GameLifecycleError("Random profile history inventory is invalid.")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("profile_value"), dict):
                raise GameLifecycleError("Random profile history entry is invalid.")
            profile_payload = row["profile_value"]
            if not isinstance(profile_payload, dict):
                raise GameLifecycleError("Random profile history payload is invalid.")
            identity = profile_payload.get("evaluation_id")
            if type(identity) is not str:
                raise GameLifecycleError("Random profile history identity is invalid.")
            historical[identity] = row
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    if manager.event_log is not decisions.event_log:
        raise GameLifecycleError("Random profile dice manager must share the engine event log.")
    rolls: dict[tuple[str, int, int, int], RandomCharacteristicRoll] = {}
    for historical_entry in historical.values():
        raw_value = historical_entry["profile_value"]
        raw_roll = historical_entry["roll"]
        if not isinstance(raw_value, dict) or not isinstance(raw_roll, dict):
            raise GameLifecycleError("Random profile history evidence is invalid.")
        historical_value = RandomProfileValue.from_payload(
            cast(RandomProfileValuePayload, raw_value)
        )
        if historical_value.characteristic is Characteristic.MOVEMENT:
            expression = historical_value.expression
            rolls["movement", expression.quantity, expression.sides, expression.modifier] = (
                RandomCharacteristicRoll.from_payload(
                    cast(RandomCharacteristicRollPayload, raw_roll)
                )
            )
    replacements: dict[str, dict[Characteristic, RandomProfileValue]] = {}
    entries: list[JsonValue] = []
    for model, value, evaluation_id in pending:
        movement = value.characteristic is Characteristic.MOVEMENT
        timing = (
            RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
            if movement
            else RandomCharacteristicTiming.PER_MODEL
        )
        expression = value.expression
        key = (
            "movement" if movement else evaluation_id,
            expression.quantity,
            expression.sides,
            expression.modifier,
        )
        prior = historical.get(evaluation_id)
        if prior is not None:
            prior_value_payload = prior["profile_value"]
            prior_roll_payload = prior["roll"]
            if not isinstance(prior_value_payload, dict) or not isinstance(
                prior_roll_payload, dict
            ):
                raise GameLifecycleError("Random profile history evidence is invalid.")
            prior_value = RandomProfileValue.from_payload(
                cast(RandomProfileValuePayload, prior_value_payload)
            )
            if replace(prior_value, evaluation=None, evaluation_id=None) != replace(
                value, evaluation=None, evaluation_id=None
            ):
                raise GameLifecycleError("Random profile descriptor changed during its evaluation.")
            rolls[key] = RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, prior_roll_payload)
            )
        if key not in rolls:
            roll_subject = (
                f"movement:{expression.canonical()}"
                if movement
                else f"{model.model_instance_id}:{value.characteristic.value}"
            )
            roll_scope = f"{scope_id}:{unit_instance_id}:{roll_subject}"
            rolls[key] = manager.roll_random_characteristic(
                characteristic=value.characteristic,
                timing=timing,
                scope_id=roll_scope,
                expression=expression,
                reason=f"Source profile {value.characteristic.value} for {unit_instance_id}",
                actor_id=player_id,
            )
        roll = rolls[key]
        evaluated = value.evaluate(
            raw=roll.value, evaluation_id=evaluation_id, target_id=model.model_instance_id
        )
        replacements.setdefault(model.model_instance_id, {})[value.characteristic] = evaluated
        entries.append(
            validate_json_value(
                {
                    "model_instance_id": model.model_instance_id,
                    "profile_value": evaluated.to_payload(),
                    "roll": roll.to_payload(),
                    "reused": prior is not None,
                }
            )
        )
    decisions.event_log.append(
        EVALUATION_EVENT_TYPE,
        cast(
            dict[str, JsonValue],
            {
                "source_rule_id": random_source.RANDOM_PROFILES_SOURCE_ID,
                "scope_id": scope_id,
                "unit_instance_id": unit_instance_id,
                "player_id": player_id,
                "battle_round": state.battle_round,
                "turn_player_id": state.active_player_id,
                "phase": None
                if state.current_battle_phase is None
                else state.current_battle_phase.value,
                "entries": entries,
            },
        ),
    )
    evaluated_models: list[ModelInstance] = []
    for model in models:
        values = replacements.get(model.model_instance_id)
        if values is None:
            evaluated_models.append(model)
            continue
        characteristics_after = tuple(
            values.get(v.characteristic, v) for v in model.characteristics
        )
        if initialize_wounds:
            if model.starting_wounds is not None or model.wounds_remaining is not None:
                raise GameLifecycleError("Random Wounds health was already initialized.")
            wounds = values[Characteristic.WOUNDS].final
            evaluated_models.append(
                replace(
                    model,
                    characteristics=characteristics_after,
                    starting_wounds=wounds,
                    wounds_remaining=wounds,
                )
            )
        else:
            evaluated_models.append(replace(model, characteristics=characteristics_after))
    return tuple(evaluated_models)
