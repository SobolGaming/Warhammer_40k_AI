from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.dice_result_override_descriptors import (
    dice_result_override_resource_entitlement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_resources import (
    UnitResourceLedger,
    UnitResourceResult,
    UnitResourceStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class UnitResourceInitialization:
    unit_instance_id: str
    resource_kind: str
    amount: int
    source_rule_id: str


def unit_resource_initializations_for_army(
    army_definition: ArmyDefinition,
) -> tuple[UnitResourceInitialization, ...]:
    initializations: list[UnitResourceInitialization] = []
    for unit in army_definition.units:
        for allocation in unit.starting_resources:
            entitlement = dice_result_override_resource_entitlement(
                abilities=unit.datasheet_abilities,
                resource_kind=allocation.resource_kind,
            )
            if entitlement is None:
                raise GameLifecycleError(
                    "Unit starting resource allocation has no source-backed entitlement."
                )
            initializations.append(
                UnitResourceInitialization(
                    unit_instance_id=unit.unit_instance_id,
                    resource_kind=allocation.resource_kind,
                    amount=allocation.amount,
                    source_rule_id=entitlement.source_rule_id,
                )
            )
    return tuple(initializations)


def seed_unit_resources(
    *,
    state: GameState,
    player_id: str,
    initializations: tuple[UnitResourceInitialization, ...],
) -> None:
    for initialization in initializations:
        initialize_unit_resource(
            state=state,
            player_id=player_id,
            unit_instance_id=initialization.unit_instance_id,
            resource_kind=initialization.resource_kind,
            amount=initialization.amount,
            source_rule_id=initialization.source_rule_id,
        )


def unit_resource_ledger_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> UnitResourceLedger | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for ledger in state.unit_resource_ledgers:
        if ledger.unit_instance_id == requested_unit_id:
            return ledger
    return None


def unit_resource_total(
    *,
    state: GameState,
    unit_instance_id: str,
    resource_kind: str,
) -> int:
    ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=unit_instance_id)
    if ledger is None:
        return 0
    return ledger.total(resource_kind)


def unit_resource_starting_total(
    *,
    state: GameState,
    unit_instance_id: str,
    resource_kind: str,
) -> int:
    ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=unit_instance_id)
    if ledger is None:
        return 0
    return ledger.starting_total(resource_kind)


def initialize_unit_resource(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    resource_kind: str,
    amount: int,
    source_rule_id: str,
) -> UnitResourceLedger:
    requested_player_id = _validate_player_id(state=state, player_id=player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if (
        _owner_player_id_for_unit(state=state, unit_instance_id=requested_unit_id)
        != requested_player_id
    ):
        raise GameLifecycleError("Unit resource initialization player ownership drift.")
    ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=requested_unit_id)
    if ledger is None:
        ledger = UnitResourceLedger.empty_for_unit(
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
        )
    updated = ledger.initialize(
        resource_kind=resource_kind,
        amount=amount,
        source_rule_id=source_rule_id,
    )
    _replace_unit_resource_ledger(state=state, updated=updated)
    return updated


def spend_unit_resource(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    resource_kind: str,
    amount: int,
    source_rule_id: str,
    decision_request_id: str,
    decision_result_id: str,
) -> UnitResourceResult:
    requested_player_id = _validate_player_id(state=state, player_id=player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if (
        _owner_player_id_for_unit(state=state, unit_instance_id=requested_unit_id)
        != requested_player_id
    ):
        raise GameLifecycleError("Unit resource spend player ownership drift.")
    ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=requested_unit_id)
    if ledger is None:
        ledger = UnitResourceLedger.empty_for_unit(
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
        )
    if ledger.player_id != requested_player_id:
        raise GameLifecycleError("Unit resource spend player ownership drift.")
    updated, result = ledger.spend(
        battle_round=state.battle_round,
        resource_kind=resource_kind,
        amount=amount,
        source_rule_id=source_rule_id,
        decision_request_id=decision_request_id,
        decision_result_id=decision_result_id,
    )
    if result.status is UnitResourceStatus.APPLIED:
        _replace_unit_resource_ledger(state=state, updated=updated)
    return result


def validate_unit_resource_ledgers(
    values: object,
    *,
    player_ids: tuple[str, ...],
    army_definitions: list[ArmyDefinition],
) -> list[UnitResourceLedger]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState unit_resource_ledgers must be a list.")
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }
    validated: list[UnitResourceLedger] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not UnitResourceLedger:
            raise GameLifecycleError(
                "GameState unit_resource_ledgers must contain UnitResourceLedger values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("UnitResourceLedger player_id is not in this game.")
        if owner_by_unit_id.get(value.unit_instance_id) != value.player_id:
            raise GameLifecycleError("UnitResourceLedger unit ownership drift.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState unit_resource_ledgers must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda ledger: ledger.unit_instance_id)


def _replace_unit_resource_ledger(*, state: GameState, updated: UnitResourceLedger) -> None:
    ledgers = [
        stored
        for stored in state.unit_resource_ledgers
        if stored.unit_instance_id != updated.unit_instance_id
    ]
    ledgers.append(updated)
    state.replace_unit_resource_ledgers(ledgers)


def _validate_player_id(*, state: GameState, player_id: str) -> str:
    requested_player_id = _validate_identifier("player_id", player_id)
    if requested_player_id not in state.player_ids:
        raise GameLifecycleError("Unit resource player_id is not in this game.")
    return requested_player_id


def _owner_player_id_for_unit(*, state: GameState, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Unit resource unit_instance_id was not found.")
