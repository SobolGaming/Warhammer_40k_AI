"""Source-backed, all-model keyword choices committed for a single move."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.rules.movement_ability import MovementAbilityDescriptor
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_super_heavy_walker_2026_09 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController

CHOICE_KEY = "move_keyword_choice"


def movement_ability_keywords(
    unit: RulesUnitView, *, include_destroyed: bool = False
) -> tuple[str, ...]:
    return tuple(
        descriptor.activation_keyword
        for descriptor in source.movement_abilities()
        if any(
            descriptor.activation_keyword in model.keywords
            for model in unit.own_models
            if include_destroyed or model.is_alive
        )
        or any(
            (include_destroyed or any(model.is_alive for model in component.unit.own_models))
            and any(
                ability.ability_id in descriptor.ability_ids
                for ability in component.unit.datasheet_abilities
            )
            for component in unit.components
        )
    )


def descriptors_for_move(
    keywords: tuple[str, ...], mode: str, *, is_surge: bool = False
) -> tuple[MovementAbilityDescriptor, ...]:
    return tuple(
        descriptor
        for descriptor in source.movement_abilities()
        if not is_surge
        and descriptor.activation_keyword in keywords
        and mode in descriptor.movement_modes
    )


def movement_keyword_options(
    *,
    options: tuple[DecisionOption, ...],
    unit: RulesUnitView,
) -> tuple[DecisionOption, ...]:
    variants: list[DecisionOption] = []
    for option in options:
        if not isinstance(option.payload, dict):
            raise GameLifecycleError("Movement keyword options require an object payload.")
        payload = option.payload
        mode = payload.get("movement_mode")
        is_surge = False
        if isinstance(payload.get("descriptor"), dict):
            movement = cast(dict[str, JsonValue], payload["descriptor"])
            mode = movement.get("movement_mode")
            is_surge = movement.get("movement_kind") == "surge"
        descriptors = descriptors_for_move(
            movement_ability_keywords(unit), str(mode), is_surge=is_surge
        )
        if not descriptors:
            variants.append(option)
            continue
        if len(descriptors) != 1:
            raise GameLifecycleError("Overlapping optional movement descriptors are unsupported.")
        descriptor = descriptors[0]
        for selected in (False, True):
            variants.append(
                replace(
                    option,
                    option_id=f"{option.option_id}:move_keywords" if selected else option.option_id,
                    label=f"{option.label} - gain {', '.join(descriptor.optional_move_keywords)}"
                    if selected
                    else option.label,
                    payload={
                        **payload,
                        CHOICE_KEY: keyword_choice_context(
                            descriptor=descriptor,
                            unit=unit,
                            selected=selected,
                        ),
                    },
                )
            )
    return tuple(variants)


def keyword_choice_context(
    *,
    descriptor: MovementAbilityDescriptor,
    unit: RulesUnitView,
    selected: bool,
) -> dict[str, JsonValue]:
    return {
        "descriptor_id": descriptor.descriptor_id,
        "source_rule_id": descriptor.source_rule_id,
        "unit_instance_id": unit.unit_instance_id,
        "model_instance_ids": validate_json_value(
            sorted(model.model_instance_id for model in unit.alive_models())
        ),
        "selected": selected,
        "keywords": list(descriptor.optional_move_keywords) if selected else [],
    }


def choice_fields(payload: object) -> dict[str, JsonValue]:
    if not isinstance(payload, dict) or CHOICE_KEY not in payload:
        return {}
    choice = cast(dict[str, object], payload)[CHOICE_KEY]
    choice_descriptor(choice)
    return {CHOICE_KEY: validate_json_value(choice)}


def choice_descriptor(choice: object) -> MovementAbilityDescriptor:
    if not isinstance(choice, dict):
        raise GameLifecycleError("Movement keyword choice must be an object.")
    row = cast(dict[str, object], choice)
    matches = tuple(
        d for d in source.movement_abilities() if d.descriptor_id == row.get("descriptor_id")
    )
    if len(matches) != 1:
        raise GameLifecycleError("Movement keyword choice has no loaded descriptor.")
    descriptor = matches[0]
    ids = row.get("model_instance_ids")
    selected = row.get("selected")
    if (
        set(row)
        != {
            "descriptor_id",
            "source_rule_id",
            "unit_instance_id",
            "model_instance_ids",
            "selected",
            "keywords",
        }
        or row["source_rule_id"] != descriptor.source_rule_id
        or type(row["unit_instance_id"]) is not str
        or type(selected) is not bool
        or not isinstance(ids, list)
        or not ids
        or any(type(value) is not str or not value for value in cast(list[object], ids))
        or ids != sorted(set(cast(list[str], ids)))
        or row["keywords"] != (list(descriptor.optional_move_keywords) if selected else [])
    ):
        raise GameLifecycleError("Movement keyword choice source or model authority drift.")
    return descriptor


def chosen_move_keywords(payload: object) -> tuple[str, ...]:
    fields = choice_fields(payload)
    if not fields:
        return ()
    choice = cast(dict[str, JsonValue], fields[CHOICE_KEY])
    descriptor = choice_descriptor(choice)
    return descriptor.optional_move_keywords if choice["selected"] else ()


def recorded_choice_fields(
    *,
    decisions: DecisionController,
    request_id: str,
    result_id: str,
) -> dict[str, JsonValue]:
    records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == request_id and record.result.result_id == result_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Movement keyword choice requires its original decision.")
    return choice_fields(records[0].result.payload)
