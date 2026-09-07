"""P01C source availability is independent of an ability's spatial requirements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleConditionKind, parameter_payload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_embarked_abilities_2026_09 as source_authority,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

EMBARKED_ABILITIES_SOURCE_ID = source_authority.EMBARKED_ABILITIES_SOURCE_ID
OFF_BATTLEFIELD_ABILITY_CONDITIONS_SOURCE_ID = (
    source_authority.OFF_BATTLEFIELD_ABILITY_CONDITIONS_SOURCE_ID
)


@dataclass(frozen=True, slots=True)
class AbilityPresence:
    rules_unit_instance_id: str
    active_model_ids: tuple[str, ...]
    battlefield_model_ids: tuple[str, ...]
    off_battlefield_model_ids: tuple[str, ...]
    unavailable_model_ids: tuple[str, ...]
    source_rule_id: str = EMBARKED_ABILITIES_SOURCE_ID


class AbilitySpatialRelationship(StrEnum):
    OWN_ABILITY = "own_ability"
    BATTLEFIELD = "battlefield"
    OFF_BATTLEFIELD = "off_battlefield"
    UNAVAILABLE = "unavailable"


def ability_presence(*, state: GameState, rules_unit: RulesUnitView) -> AbilityPresence:
    """Read current living membership and explicit placement/cargo/reserve authority.

    An unplaced model with no cargo/reserve authority is unavailable, never an
    implicit off-battlefield source. Conflicting presence fails before execution.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Ability presence requires GameState and RulesUnitView.")
    current = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit.unit_instance_id)
    alive = {model.model_instance_id for model in current.alive_models()}
    placed = (
        set[str]()
        if state.battlefield_state is None
        else set(state.battlefield_state.placed_model_ids())
    ) & alive
    off_board = (set(state.embarked_model_ids()) | set(state.unarrived_reserve_model_ids())) & alive
    return ability_presence_from_model_ids(
        rules_unit_instance_id=current.unit_instance_id,
        alive_model_ids=alive,
        battlefield_model_ids=placed,
        off_battlefield_model_ids=off_board,
    )


def ability_presence_from_model_ids(
    *,
    rules_unit_instance_id: str,
    alive_model_ids: set[str],
    battlefield_model_ids: set[str],
    off_battlefield_model_ids: set[str],
) -> AbilityPresence:
    """Shared live/historical policy over explicitly authenticated model facts."""
    alive = alive_model_ids
    placed = battlefield_model_ids & alive
    off_board = off_battlefield_model_ids & alive
    if placed & off_board or (placed and off_board):
        raise GameLifecycleError("Ability source has conflicting rules-unit presence.")
    unavailable = alive - placed - off_board
    if off_board and unavailable:
        raise GameLifecycleError("Ability source has incomplete off-battlefield membership.")
    return AbilityPresence(
        rules_unit_instance_id=rules_unit_instance_id,
        active_model_ids=tuple(sorted(placed | off_board)),
        battlefield_model_ids=tuple(sorted(placed)),
        off_battlefield_model_ids=tuple(sorted(off_board)),
        unavailable_model_ids=tuple(sorted(unavailable)),
    )


def active_ability_model_ids_for_unit(*, state: GameState, unit: UnitInstance) -> tuple[str, ...]:
    """Resolve current physical ownership, including attached/split components."""
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Ability source requires a UnitInstance.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    component = next(
        (
            value.unit
            for value in view.components
            if value.unit.unit_instance_id == unit.unit_instance_id
        ),
        None,
    )
    if component is None:
        raise GameLifecycleError("Ability source requires a physical component unit.")
    own_ids = set(component.own_model_ids())
    return tuple(
        model_id
        for model_id in ability_presence(state=state, rules_unit=view).active_model_ids
        if model_id in own_ids
    )


def ability_spatial_relationship(
    *,
    state: GameState,
    source: RulesUnitView,
    target: RulesUnitView,
    source_model_instance_id: str | None = None,
) -> AbilitySpatialRelationship:
    """01.02.04: self visibility/range survives; another unit needs geometry."""
    source_presence = ability_presence(state=state, rules_unit=source)
    target_presence = ability_presence(state=state, rules_unit=target)
    if source_model_instance_id is not None:
        source.component_unit_for_model(source_model_instance_id)
    return ability_spatial_relationship_from_presence(
        source_presence=source_presence,
        target_presence=target_presence,
        source_model_instance_id=source_model_instance_id,
    )


def ability_spatial_relationship_from_presence(
    *,
    source_presence: AbilityPresence,
    target_presence: AbilityPresence,
    source_model_instance_id: str | None = None,
) -> AbilitySpatialRelationship:
    """One spatial policy for current state and authenticated historical state."""
    if (
        not source_presence.active_model_ids
        or not target_presence.active_model_ids
        or (
            source_model_instance_id is not None
            and source_model_instance_id not in source_presence.active_model_ids
        )
    ):
        return AbilitySpatialRelationship.UNAVAILABLE
    if source_presence.rules_unit_instance_id == target_presence.rules_unit_instance_id:
        return AbilitySpatialRelationship.OWN_ABILITY
    if source_presence.off_battlefield_model_ids or target_presence.off_battlefield_model_ids:
        return AbilitySpatialRelationship.OFF_BATTLEFIELD
    return AbilitySpatialRelationship.BATTLEFIELD


def ability_battlefield_conditions_apply(
    *,
    state: GameState,
    clause: RuleClause,
    source_unit_instance_id: str,
    source_model_instance_id: str,
) -> bool:
    """Enforce explicit typed source-presence restrictions, independent of activation."""
    view = rules_unit_view_by_id(state=state, unit_instance_id=source_unit_instance_id)
    presence = ability_presence(state=state, rules_unit=view)
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
            continue
        relationship = parameter_payload(condition.parameters).get("relationship")
        if (
            relationship == "source_model_on_battlefield"
            and source_model_instance_id not in presence.battlefield_model_ids
        ):
            return False
    return True


__all__ = (
    "OFF_BATTLEFIELD_ABILITY_CONDITIONS_SOURCE_ID",
    "AbilityPresence",
    "AbilitySpatialRelationship",
    "ability_battlefield_conditions_apply",
    "ability_presence",
    "ability_spatial_relationship",
    "active_ability_model_ids_for_unit",
)
