"""Strict decoder for the grouped Combat payload produced by the movement owner."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.hazard import hazard_roll_failed
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import (
    RulesUnitPlacement,
    RulesUnitPlacementPayload,
)
from warhammer40k_core.engine.transports import (
    DestroyedTransportModelRoll,
    DestroyedTransportModelRollPayload,
    DisembarkedUnitState,
    DisembarkedUnitStatePayload,
    TransportCargoState,
    TransportCargoStatePayload,
    TransportOperationViolation,
    TransportOperationViolationPayload,
    TransportRestrictionOverride,
    TransportRestrictionOverridePayload,
    disembark_mode_kind_from_token,
    transport_movement_status_from_token,
)
from warhammer40k_core.engine.unit_coherency import UnitCoherencyResult, UnitCoherencyResultPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitCombatDisembarkResolution,
        RulesUnitDisembarkResolution,
    )


def rules_unit_combat_from_payload(payload: JsonValue) -> RulesUnitCombatDisembarkResolution:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitCombatDisembarkModelRoll,
        RulesUnitCombatDisembarkResolution,
    )

    value = _object(payload)
    rolls = tuple(_object(row) for row in _array(value["model_rolls"]))
    result = RulesUnitCombatDisembarkResolution(
        placement=_placement(value["placement"]),
        tactical_resolution=_placement(value["tactical_resolution"]),
        model_rolls=tuple(
            RulesUnitCombatDisembarkModelRoll(
                component_unit_instance_id=_identifier(row["component_unit_instance_id"]),
                roll=DestroyedTransportModelRoll.from_payload(
                    cast(DestroyedTransportModelRollPayload, _object(row["roll"]))
                ),
                mortal_wounds_per_failed_roll=_integer(row["mortal_wounds_per_failed_roll"]),
            )
            for row in rolls
        ),
    )
    selection = result.placement.selection
    tactical = result.tactical_resolution.selection
    if (
        selection.player_id != tactical.player_id
        or selection.battle_round != tactical.battle_round
        or selection.unit_instance_id != tactical.unit_instance_id
        or selection.transport_unit_instance_id != tactical.transport_unit_instance_id
        or selection.transport_movement_status != tactical.transport_movement_status
        or selection.restriction_overrides != tactical.restriction_overrides
        or {
            (component.unit_instance_id, row.model_instance_id)
            for component in selection.attempted_placement.component_unit_placements
            for row in component.model_placements
        }
        != {
            (component.unit_instance_id, row.model_instance_id)
            for component in tactical.attempted_placement.component_unit_placements
            for row in component.model_placements
        }
    ):
        raise GameLifecycleError("Rules-unit Combat Tactical context identity drift.")
    if not result.is_valid:
        raise GameLifecycleError("Rules-unit Combat hazard requires a valid admitted placement.")
    for row in result.model_rolls:
        if row.roll.mortal_wound_inflicted != hazard_roll_failed(row.roll.roll_state):
            raise GameLifecycleError("Rules-unit Combat hazard roll outcome drift.")
    # Exact JSON comparison keeps repeated derived fields, boolean/number distinctions,
    # extra fields and all nested derived totals under the producer's authority.
    if canonical_json(validate_json_value(result.to_payload())) != canonical_json(payload):
        raise GameLifecycleError("Rules-unit Combat payload differs from its typed records.")
    return result


def _placement(payload: JsonValue) -> RulesUnitDisembarkResolution:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitDisembarkResolution,
        RulesUnitDisembarkSelection,
    )

    value = _object(payload)
    selected = _object(value["selection"])
    selection = RulesUnitDisembarkSelection(
        player_id=_identifier(selected["player_id"]),
        battle_round=_integer(selected["battle_round"]),
        unit_instance_id=_identifier(selected["unit_instance_id"]),
        transport_unit_instance_id=_identifier(selected["transport_unit_instance_id"]),
        attempted_placement=RulesUnitPlacement.from_payload(
            cast(RulesUnitPlacementPayload, _object(selected["attempted_rules_unit_placement"]))
        ),
        disembark_mode=disembark_mode_kind_from_token(_identifier(selected["disembark_mode"])),
        transport_movement_status=transport_movement_status_from_token(
            _identifier(selected["transport_movement_status"])
        ),
        restriction_overrides=tuple(
            TransportRestrictionOverride.from_payload(
                cast(TransportRestrictionOverridePayload, _object(row))
            )
            for row in _array(selected["restriction_overrides"])
        ),
        start_engaged_enemy_unit_instance_ids=tuple(
            _identifier(row) for row in _array(selected["start_engaged_enemy_unit_instance_ids"])
        ),
    )
    cargo, state, transition = (
        value["updated_cargo_state"],
        value["disembarked_unit_state"],
        value["transition_batch"],
    )
    result = RulesUnitDisembarkResolution(
        selection=selection,
        violations=tuple(
            TransportOperationViolation.from_payload(
                cast(TransportOperationViolationPayload, _object(row))
            )
            for row in _array(value["violations"])
        ),
        coherency_result=UnitCoherencyResult.from_payload(
            cast(UnitCoherencyResultPayload, _object(value["coherency_result"]))
        ),
        updated_cargo_state=None
        if cargo is None
        else TransportCargoState.from_payload(cast(TransportCargoStatePayload, _object(cargo))),
        disembarked_unit_state=None
        if state is None
        else DisembarkedUnitState.from_payload(cast(DisembarkedUnitStatePayload, _object(state))),
        transition_batch=None
        if transition is None
        else BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, _object(transition))
        ),
    )
    if result.is_valid:
        expected_state = DisembarkedUnitState.for_mode(
            player_id=selection.player_id,
            battle_round=selection.battle_round,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            disembark_mode=selection.disembark_mode,
            transport_movement_status=selection.transport_movement_status,
            restriction_overrides=selection.restriction_overrides,
        )
        if result.disembarked_unit_state != expected_state:
            raise GameLifecycleError("Rules-unit Combat disembarked state identity drift.")
        if result.updated_cargo_state is None or (
            result.updated_cargo_state.player_id != selection.player_id
            or result.updated_cargo_state.transport_unit_instance_id
            != selection.transport_unit_instance_id
            or any(
                result.updated_cargo_state.contains_unit(component)
                for component in selection.attempted_placement.component_unit_instance_ids
            )
        ):
            raise GameLifecycleError("Rules-unit Combat cargo identity drift.")
    if canonical_json(validate_json_value(result.to_payload())) != canonical_json(payload):
        raise GameLifecycleError("Rules-unit Combat placement payload drift.")
    return result


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Rules-unit Combat payload requires an object.")
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise GameLifecycleError("Rules-unit Combat payload requires an array.")
    return value


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise GameLifecycleError("Rules-unit Combat payload requires an identifier.")
    return value


def _integer(value: JsonValue) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError("Rules-unit Combat payload requires a positive integer.")
    return value
