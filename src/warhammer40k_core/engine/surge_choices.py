"""Finite closest-target choices carried into the existing reactive path proposal."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.surge_movement import closest_surge_targets
from warhammer40k_core.engine.take_to_the_skies import flight_choice_context

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementDescriptor


def surge_target_options(
    *, state: GameState, options: tuple[DecisionOption, ...]
) -> tuple[DecisionOption, ...]:
    scenario = battlefield_scenario_for_state(state=state)
    result: list[DecisionOption] = []
    for option in options:
        payload = option.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Surge options require object payloads.")
        if payload.get("declined"):
            result.append(option)
            continue
        unit_id = payload.get("unit_instance_id")
        if not isinstance(unit_id, str):
            raise GameLifecycleError("Surge option requires a source unit.")
        view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        targets = closest_surge_targets(scenario=scenario, unit_instance_id=view.unit_instance_id)
        for target in targets:
            result.append(
                replace(
                    option,
                    option_id=f"surge:{view.unit_instance_id}:target:{target}",
                    label=f"Surge {view.unit_instance_id} towards {target}",
                    payload={
                        **payload,
                        "unit_instance_id": view.unit_instance_id,
                        "surge_target_unit_instance_id": target,
                        "closest_target_unit_instance_ids": list(targets),
                        **flight_choice_context(
                            unit=view, ruleset=state.runtime_ruleset_descriptor(), selected=False
                        ),
                    },
                )
            )
    return tuple(result)


def selected_surge_target(
    payload: JsonValue, descriptor: TriggeredMovementDescriptor
) -> str | None:
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementKind

    if descriptor.movement_kind is not TriggeredMovementKind.SURGE:
        return None
    if not isinstance(payload, dict) or not isinstance(
        payload.get("surge_target_unit_instance_id"), str
    ):
        raise GameLifecycleError("Surge requires its original finite target commitment.")
    target = payload["surge_target_unit_instance_id"]
    if not isinstance(target, str):
        raise GameLifecycleError("Surge target must be a string.")
    return target


def surge_choice_context(
    payload: JsonValue, descriptor: TriggeredMovementDescriptor
) -> dict[str, JsonValue]:
    target = selected_surge_target(payload, descriptor)
    return {} if target is None else {"surge_target_unit_instance_id": target}
