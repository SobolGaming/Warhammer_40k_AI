"""Source-linked, per-move flight choices shared by movement consumers."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_flying_2026_09 import (
    TAKE_TO_THE_SKIES_SOURCE_ID as TAKE_TO_THE_SKIES_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def flight_choices(
    *, option: DecisionOption, unit: RulesUnitView, ruleset: RulesetDescriptor
) -> tuple[DecisionOption, ...]:
    if not isinstance(option.payload, dict):
        raise GameLifecycleError("Flight options require an object payload.")
    model_ids = sorted(
        model.model_instance_id for model in unit.alive_models() if "FLY" in model.keywords
    )
    choices = (
        (False, True) if model_ids and ruleset.fly_policy.take_to_the_skies_supported else (False,)
    )
    return tuple(
        replace(
            option,
            option_id=f"{option.option_id}:take_to_the_skies" if selected else option.option_id,
            label=f"{option.label} - Take to the Skies" if selected else option.label,
            payload={
                **option.payload,
                **flight_choice_context(unit=unit, ruleset=ruleset, selected=selected),
            },
        )
        for selected in choices
    )


def flight_choice_context(
    *, unit: RulesUnitView, ruleset: RulesetDescriptor, selected: bool
) -> dict[str, JsonValue]:
    return {
        "take_to_the_skies": selected,
        "flying_model_instance_ids": validate_json_value(
            sorted(
                model.model_instance_id for model in unit.alive_models() if "FLY" in model.keywords
            )
        ),
        "flight_penalty_inches": flight_penalty(unit=unit, ruleset=ruleset) if selected else 0.0,
    }


def flight_selection(payload: object) -> bool:
    if (
        not isinstance(payload, dict)
        or type(cast(dict[str, object], payload).get("take_to_the_skies")) is not bool
    ):
        raise GameLifecycleError("Take to the Skies requires an explicit finite move choice.")
    return cast(bool, payload["take_to_the_skies"])


def validate_flight_context(
    *, payload: object, unit: RulesUnitView, ruleset: RulesetDescriptor
) -> None:
    selected = flight_selection(payload)
    expected = flight_choice_context(unit=unit, ruleset=ruleset, selected=selected)
    if not isinstance(payload, dict) or any(
        cast(dict[str, object], payload).get(key) != value for key, value in expected.items()
    ):
        raise GameLifecycleError("Take to the Skies model membership or Hover authority drift.")


def flight_penalty(*, unit: RulesUnitView, ruleset: RulesetDescriptor) -> float:
    if "FLY" not in unit.keywords or not ruleset.fly_policy.take_to_the_skies_supported:
        raise GameLifecycleError("Take to the Skies requires an eligible FLY rules unit.")
    return 0.0 if "HOVER" in unit.keywords else ruleset.fly_policy.movement_penalty_inches


def selected_charge_flight(state: GameState) -> bool:
    phase = state.charge_phase_state
    if phase is None or phase.active_selection is None:
        raise GameLifecycleError("Charge flight requires its committed selection.")
    pending = phase.move_pending_distance_state()
    selected = phase.active_selection.take_to_the_skies
    if pending is not None and pending.roll_result.request.take_to_the_skies != selected:
        raise GameLifecycleError("Charge flight differs from its committed roll.")
    return selected
