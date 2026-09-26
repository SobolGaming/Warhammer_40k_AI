"""Authenticate evaluated model profile values against catalog and physical dice."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
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
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_evaluation import (
    EVALUATION_EVENT_TYPE,
)
from warhammer40k_core.engine.random_profile_inventory import historical_profile_models
from warhammer40k_core.engine.random_profile_roll_authority import validate_profile_roll
from warhammer40k_core.engine.random_profile_scope_authority import validate_profile_scope
from warhammer40k_core.engine.rules_units import rules_unit_identity_history_contains
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_random_profiles_2026_09 as random_source,
)


def validate_random_profile_history(
    *,
    state: GameState,
    catalog: ArmyCatalog | None,
    config: GameConfig | None = None,
    pending_requests: tuple[DecisionRequest, ...] = (),
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if not any(event.event_type == EVALUATION_EVENT_TYPE for event in event_records):
        if any(
            isinstance(v, RandomProfileValue) and v.evaluation is not None
            for a in state.army_definitions
            for u in a.units
            for m in u.own_models
            for v in m.characteristics
        ):
            raise GameLifecycleError("Random profile evaluation history is absent.")
        return
    models, owners, physical_units = historical_profile_models(
        state=state,
        config=config,
        requests=(*tuple(record.request for record in decision_records), *pending_requests),
    )
    current_models = {
        m.model_instance_id: m
        for a in state.army_definitions
        for u in a.units
        for m in u.own_models
    }
    latest: dict[tuple[str, Characteristic], RandomProfileValue] = {}
    seen_ids: dict[str, dict[str, JsonValue]] = {}
    dice: dict[str, JsonValue] = {}
    random_rolls: set[str] = set()
    decisions = {r.result.result_id: r for r in decision_records}
    group_rolls: dict[tuple[str, str, int, int, int], str] = {}
    roll_groups: dict[str, tuple[str, str, int, int, int]] = {}
    for event_index, event in enumerate(event_records):
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        if event.event_type == "catalog_unit_datasheet_replaced":
            retained = payload.get("retained_model_instance_ids")
            pruned = payload.get("pruned_model_instance_ids")
            if not isinstance(retained, list) or not isinstance(pruned, list):
                raise GameLifecycleError("Random profile datasheet handoff inventory is invalid.")
            for model_id in (*retained, *pruned):
                if type(model_id) is not str:
                    raise GameLifecycleError("Random profile datasheet handoff model is invalid.")
                latest = {key: value for key, value in latest.items() if key[0] != model_id}
                if model_id in current_models:
                    models[model_id] = current_models[model_id]
        if event.event_type == "dice_rolled":
            roll_id = payload.get("roll_id")
            if type(roll_id) is str:
                dice[roll_id] = payload
        if event.event_type == "random_characteristic_rolled":
            random_rolls.add(canonical_json(payload))
        if event.event_type != EVALUATION_EVENT_TYPE:
            continue
        if (
            set(payload)
            != {
                "source_rule_id",
                "scope_id",
                "unit_instance_id",
                "player_id",
                "battle_round",
                "turn_player_id",
                "phase",
                "entries",
            }
            or payload.get("source_rule_id") != random_source.RANDOM_PROFILES_SOURCE_ID
        ):
            raise GameLifecycleError("Random profile source authority drifted.")
        scope = payload.get("scope_id")
        unit_id = payload.get("unit_instance_id")
        entries = payload.get("entries")
        if (
            type(scope) is not str
            or type(unit_id) is not str
            or not isinstance(entries, list)
            or not entries
        ):
            raise GameLifecycleError("Random profile evaluation scope or inventory is invalid.")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "model_instance_id",
                "profile_value",
                "roll",
                "reused",
            }:
                raise GameLifecycleError("Random profile evaluation entry is invalid.")
            model_id = entry["model_instance_id"]
            if type(model_id) is not str or model_id not in models:
                raise GameLifecycleError("Random profile evaluation model is unknown.")
            value_payload = entry["profile_value"]
            roll_payload = entry["roll"]
            if not isinstance(value_payload, dict) or not isinstance(roll_payload, dict):
                raise GameLifecycleError("Random profile value or dice evidence is invalid.")
            value = RandomProfileValue.from_payload(cast(RandomProfileValuePayload, value_payload))
            roll = RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, roll_payload)
            )
            expected_id = f"{scope}:{unit_id}:{model_id}:{value.characteristic.value}"
            reused = entry["reused"]
            if type(reused) is not bool:
                raise GameLifecycleError("Random profile reuse flag is invalid.")
            previous_entry = seen_ids.get(expected_id)
            if (
                value.evaluation_id != expected_id
                or (previous_entry is not None) != reused
                or (reused and previous_entry != {k: v for k, v in entry.items() if k != "reused"})
            ):
                raise GameLifecycleError(
                    "Random profile occurrence identity drifted or duplicated."
                )
            seen_ids[expected_id] = {k: v for k, v in entry.items() if k != "reused"}
            if (
                value.evaluation
                != value.evaluate(
                    raw=roll.value, evaluation_id=expected_id, target_id=model_id
                ).evaluation
            ):
                raise GameLifecycleError("Random profile resolved value drifted from dice.")
            original = roll.roll_state.original_result
            player_id = payload.get("player_id")
            if type(player_id) is not str:
                raise GameLifecycleError("Random profile player identity is invalid.")
            validate_profile_scope(
                state=state,
                scope=scope,
                unit_id=unit_id,
                player_id=player_id,
                characteristic=value.characteristic,
                body=payload,
                events=event_records,
                prior_events=event_records[:event_index],
                requests=(*tuple(record.request for record in decision_records), *pending_requests),
                decisions=decision_records,
            )
            movement = value.characteristic is Characteristic.MOVEMENT
            roll_subject = (
                f"movement:{value.expression.canonical()}"
                if movement
                else f"{model_id}:{value.characteristic.value}"
            )
            validate_profile_roll(
                roll=roll,
                value=value,
                scope_id=f"{scope}:{unit_id}:{roll_subject}",
                timing=RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
                if movement
                else RandomCharacteristicTiming.PER_MODEL,
                actor_id=player_id,
                reason=f"Source profile {value.characteristic.value} for {unit_id}",
                physical_rolls=dice,
                random_rolls=random_rolls,
            )
            if catalog is None:
                raise GameLifecycleError(
                    "Random profile restore requires the authoritative catalog."
                )
            model = models[model_id]
            if owners.get(model_id) != player_id:
                raise GameLifecycleError("Random profile model owner drifted.")
            if not rules_unit_identity_history_contains(
                state=state, identity_ids=(unit_id,), unit_instance_id=physical_units[model_id]
            ):
                raise GameLifecycleError("Random profile model is not in the evaluated rules unit.")
            current_descriptor = model.characteristic(value.characteristic)
            if (
                not isinstance(current_descriptor, RandomProfileValue)
                or current_descriptor.modifiers != value.modifiers
            ):
                raise GameLifecycleError("Random profile bound modifiers drifted.")
            source = (
                catalog.datasheet_by_id(model.datasheet_id)
                .model_profile_by_id(model.model_profile_id)
                .characteristic(value.characteristic)
            )
            if (
                not isinstance(source, RandomProfileValue)
                or replace(value, evaluation=None, evaluation_id=None, modifiers=()) != source
            ):
                raise GameLifecycleError(
                    "Random profile descriptor drifted from its catalog source."
                )
            if value.characteristic is Characteristic.MOVEMENT:
                decision = decisions.get(scope)
                if decision is None or decision.result.actor_id != payload.get("player_id"):
                    raise GameLifecycleError("Random Movement lacks its accepted selection.")
                if decision.request.decision_type == "select_movement_unit":
                    if decision.result.selected_option_id != unit_id:
                        raise GameLifecycleError("Random Movement selected unit drifted.")
                elif not any(
                    item.event_type == "active_player_scope_started"
                    and isinstance(item.payload, dict)
                    and item.payload.get("kind") == "reactive_move"
                    and item.payload.get("selection_result_id") == scope
                    and item.payload.get("selection_request_id") == decision.request.request_id
                    and item.payload.get("unit_instance_id") == unit_id
                    and item.payload.get("player_id") == player_id
                    for item in event_records
                ):
                    raise GameLifecycleError("Random Movement lacks its reactive selection.")
                expression = value.expression
                group = (scope, unit_id, expression.quantity, expression.sides, expression.modifier)
                previous = group_rolls.setdefault(group, original.roll_id)
                previous_group = roll_groups.setdefault(original.roll_id, group)
                if previous != original.roll_id or previous_group != group:
                    raise GameLifecycleError("Random Movement expression roll-sharing drifted.")
            latest[model_id, value.characteristic] = value
    for model_id, model in current_models.items():
        for current_value in model.characteristics:
            if isinstance(current_value, RandomProfileValue):
                value = current_value
                expected = latest.get((model_id, value.characteristic))
                if value.evaluation is not None and expected != value:
                    raise GameLifecycleError(
                        "Random profile current evaluation is not authenticated."
                    )
                if value.evaluation is None and expected is not None:
                    raise GameLifecycleError("Random profile current evaluation is missing.")
