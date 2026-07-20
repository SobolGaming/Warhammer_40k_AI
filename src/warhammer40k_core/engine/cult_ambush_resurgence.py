from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitComponent, rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_CULT_AMBUSH_ABILITY_IDS = frozenset({"cult-ambush"})
_RESURGENCE_COSTS_BY_DATASHEET_ID = {
    "aberrants": {5: 4, 10: 8},
    "acolyte-hybrids-with-autopistols": {5: 2, 10: 4},
    "acolyte-hybrids-with-hand-flamers": {5: 2, 10: 4},
    "atalan-jackals": {5: 2, 10: 6},
    "hybrid-metamorphs": {5: 2, 10: 4},
    "neophyte-hybrids": {10: 3, 20: 6},
    "purestrain-genestealers": {5: 2, 10: 6},
}
_RESURGENCE_COSTS_BY_UNIT_NAME = {
    "ABERRANTS": {5: 4, 10: 8},
    "ACOLYTE HYBRIDS WITH AUTOPISTOLS": {5: 2, 10: 4},
    "ACOLYTE HYBRIDS WITH HAND FLAMERS": {5: 2, 10: 4},
    "ATALAN JACKALS": {5: 2, 10: 6},
    "HYBRID METAMORPHS": {5: 2, 10: 4},
    "NEOPHYTE HYBRIDS": {10: 3, 20: 6},
    "PURESTRAIN GENESTEALERS": {5: 2, 10: 6},
}


@dataclass(frozen=True, slots=True)
class CultAmbushReturnCandidate:
    unit: UnitInstance
    starting_strength: int
    source_rule_ids: tuple[str, ...] = ()


def cult_ambush_return_candidate(
    state: GameState,
    *,
    destroyed_unit_instance_id: str,
) -> CultAmbushReturnCandidate | None:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=destroyed_unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        unit = rules_unit.components[0].unit
        if not _unit_has_cult_ambush_ability(unit):
            return None
        starting_strength = state.starting_strength_record_for_unit(
            unit.unit_instance_id
        ).starting_model_count
        return CultAmbushReturnCandidate(unit=unit, starting_strength=starting_strength)

    tacoma_overlay_active = tacoma_open_2026.is_active(state.rules_overlay_ids)
    if destroyed_unit_instance_id == rules_unit.unit_instance_id or not tacoma_overlay_active:
        included_components = tuple(
            component
            for component in rules_unit.components
            if not (tacoma_overlay_active and _is_attached_character_component(component))
        )
    else:
        included_components = tuple(
            component
            for component in rules_unit.components
            if component.unit.unit_instance_id == destroyed_unit_instance_id
            and not (tacoma_overlay_active and _is_attached_character_component(component))
        )
    if not included_components:
        return None
    if any(not _unit_has_cult_ambush_ability(component.unit) for component in included_components):
        return None
    if len(included_components) != 1:
        raise GameLifecycleError(
            "Cult Ambush cannot return an attached unit with multiple non-CHARACTER components."
        )
    unit = included_components[0].unit
    excluded_attached_character = tacoma_overlay_active and len(included_components) != len(
        rules_unit.components
    )
    return CultAmbushReturnCandidate(
        unit=unit,
        starting_strength=sum(len(component.unit.own_models) for component in included_components),
        source_rule_ids=(
            (tacoma_open_2026.CULT_AMBUSH_ATTACHED_CHARACTER_EXCLUSION_SOURCE_ID,)
            if excluded_attached_character
            else ()
        ),
    )


def cult_ambush_resurgence_cost_for_unit(state: GameState, unit: UnitInstance) -> int | None:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Cult Ambush cost requires UnitInstance.")
    candidate = cult_ambush_return_candidate(
        state,
        destroyed_unit_instance_id=unit.unit_instance_id,
    )
    if candidate is None:
        return None
    return resurgence_cost(unit=candidate.unit, starting_strength=candidate.starting_strength)


def resurgence_cost(*, unit: UnitInstance, starting_strength: int) -> int | None:
    costs = _RESURGENCE_COSTS_BY_DATASHEET_ID.get(unit.datasheet_id)
    if costs is None:
        costs = _RESURGENCE_COSTS_BY_UNIT_NAME.get(unit.name.upper())
    if costs is None:
        return None
    return costs.get(starting_strength)


def replacement_unit_for_destroyed_unit(
    state: GameState,
    destroyed_unit: UnitInstance,
) -> UnitInstance:
    new_unit_id = _next_replacement_unit_id(state, destroyed_unit.unit_instance_id)
    new_models: list[ModelInstance] = []
    for index, model in enumerate(destroyed_unit.own_models, start=1):
        new_models.append(
            replace(
                model,
                model_instance_id=f"{new_unit_id}:model-{index:03d}",
                wounds_remaining=model.starting_wounds,
            )
        )
    return replace(destroyed_unit, unit_instance_id=new_unit_id, own_models=tuple(new_models))


def _next_replacement_unit_id(state: GameState, destroyed_unit_id: str) -> str:
    existing_ids = {unit.unit_instance_id for army in state.army_definitions for unit in army.units}
    index = 1
    while True:
        candidate = f"{destroyed_unit_id}:cult-ambush-{index:03d}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def _unit_has_cult_ambush_ability(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Cult Ambush eligibility requires UnitInstance.")
    return any(
        ability.ability_id in _CULT_AMBUSH_ABILITY_IDS for ability in unit.datasheet_abilities
    )


def _is_attached_character_component(component: RulesUnitComponent) -> bool:
    if component.role not in {"leader", "support"}:
        return False
    return any(keyword.upper() == "CHARACTER" for keyword in component.unit.keywords)
