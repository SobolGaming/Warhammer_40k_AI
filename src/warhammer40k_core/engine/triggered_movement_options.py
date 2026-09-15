"""Finite reactive Normal-move choices, including per-move flight authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.take_to_the_skies import flight_choices

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementEligibleUnit,
    )


def triggered_movement_unit_selection_options(
    *,
    state: GameState,
    descriptor: TriggeredMovementDescriptor,
    eligible_units: tuple[TriggeredMovementEligibleUnit, ...],
) -> tuple[DecisionOption, ...]:
    from warhammer40k_core.engine.triggered_movement import (
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
    )

    options: list[DecisionOption] = []
    if descriptor.optional:
        options.append(
            DecisionOption(
                option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
                label="Decline Triggered Movement",
                payload=validate_json_value(
                    {
                        "triggered_movement_kind": descriptor.movement_kind.value,
                        "displacement_kind": descriptor.displacement_kind.value,
                        "descriptor": descriptor.to_payload(),
                        "source_rule_id": descriptor.source_rule_id,
                        "trigger_timing": descriptor.trigger_timing.to_payload(),
                        "movement_phase_action": None,
                        "requires_movement_proposal": False,
                        "declined": True,
                    }
                ),
            )
        )
    for unit in eligible_units:
        options.append(
            DecisionOption(
                option_id=f"{descriptor.movement_kind.value}:{unit.unit_instance_id}",
                label=f"{descriptor.movement_kind.value.title()} {unit.unit_instance_id}",
                payload=validate_json_value(
                    {
                        "triggered_movement_kind": descriptor.movement_kind.value,
                        "displacement_kind": descriptor.displacement_kind.value,
                        "unit_instance_id": unit.unit_instance_id,
                        "descriptor": descriptor.to_payload(),
                        "source_rule_id": descriptor.source_rule_id,
                        "trigger_timing": descriptor.trigger_timing.to_payload(),
                        "movement_phase_action": TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
                        "requires_movement_proposal": True,
                        "eligible_unit": unit.to_payload(),
                    }
                ),
            )
        )
    return tuple(
        variant
        for option in options
        for variant in (
            flight_choices(
                option=option,
                unit=rules_unit_view_by_id(
                    state=state, unit_instance_id=str(option.payload["unit_instance_id"])
                ),
                ruleset=state.runtime_ruleset_descriptor(),
            )
            if descriptor.movement_mode is MovementMode.NORMAL
            and isinstance(option.payload, dict)
            and not option.payload.get("declined")
            else (option,)
        )
    )
