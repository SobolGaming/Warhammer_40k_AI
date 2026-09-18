"""Applicable, source-backed core grants join the native occurrence inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ability_sources import AbilitySourceInstance
from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.core_ability_state import core_instance_groups
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.unit_factory import UnitInstance

_BINDING_FAMILIES = {
    "core-stealth": CoreAbilityFamily.STEALTH,
    "core-lone-operative": CoreAbilityFamily.LONE_OPERATIVE,
}


def core_ability_inventory(
    *,
    state: GameState,
    unit: UnitInstance,
    registry: RuntimeModifierRegistry,
) -> tuple[tuple[CoreAbilityFamily, tuple[AbilitySourceInstance, ...]], ...]:
    from warhammer40k_core.engine.catalog_conditional_leader_queries import (
        conditional_granted_ability_effects_for_unit,
    )
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.stealth import stealth_source_inventory

    groups = {family: list(sources) for family, sources in core_instance_groups(unit)}
    if not _has_runtime_core_grants(state, registry):
        return tuple((family, tuple(sources)) for family, sources in sorted(groups.items()))
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    native_fight_effect_ids = {
        f"{source.instance_id}:fights-first"
        for component in view.components
        for family, sources in core_instance_groups(component.unit)
        if family is CoreAbilityFamily.FIGHTS_FIRST
        for source in sources
    }
    for source in FightsFirstRegistry.from_state(state).sources:
        if (
            source.unit_instance_id == view.unit_instance_id
            and source.effect_id not in native_fight_effect_ids
        ):
            _add(
                groups,
                unit,
                CoreAbilityFamily.FIGHTS_FIRST,
                source.source_rule_id,
                source.effect_id,
            )
    for effect in conditional_granted_ability_effects_for_unit(
        state=state,
        rules_unit_instance_id=view.unit_instance_id,
        component_unit_instance_id=unit.unit_instance_id,
        ability="infiltrators",
    ):
        _add(groups, unit, CoreAbilityFamily.INFILTRATORS, effect.source_rule_id, effect.effect_id)
    _, _, commitments = stealth_source_inventory(
        state=state, target_unit_instance_id=view.unit_instance_id
    )
    for commitment in commitments:
        if not isinstance(commitment, dict) or "effect" not in commitment:
            continue  # Native model evidence is already represented by descriptor occurrences.
        affected = cast(list[str], commitment["model_ids"])
        if not set(unit.own_model_ids()).intersection(affected):
            continue
        effect_payload = cast(dict[str, JsonValue], commitment["effect"])
        source_id, effect_id = effect_payload["source_rule_id"], effect_payload["effect_id"]
        if type(source_id) is not str or type(effect_id) is not str:
            from warhammer40k_core.engine.phase import GameLifecycleError

            raise GameLifecycleError("Core grant effect identity drift.")
        _add(groups, unit, CoreAbilityFamily.STEALTH, source_id, effect_id)
    context = ModelAbilityGrantContext(state, view)
    for binding in registry.model_ability_grant_bindings:
        family = _BINDING_FAMILIES.get(binding.ability_id)
        if family is not None and set(binding.model_ids(context)).intersection(
            unit.own_model_ids()
        ):
            _add(groups, unit, family, binding.source_id, binding.modifier_id)
    return tuple(
        (family, tuple(sorted(sources, key=lambda source: source.instance_id)))
        for family, sources in sorted(groups.items())
    )


def _has_runtime_core_grants(state: GameState, registry: RuntimeModifierRegistry) -> bool:
    """Avoid spatial/effect queries when no runtime producer can add a Core source."""
    from warhammer40k_core.engine.fights_first import (
        CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        FIGHTS_FIRST_EFFECT_KIND,
    )
    from warhammer40k_core.engine.generic_rule_effect_payloads import (
        generic_rule_effect_payload_grants_ability,
    )

    if any(
        binding.ability_id in _BINDING_FAMILIES for binding in registry.model_ability_grant_bindings
    ):
        return True
    return any(
        isinstance(payload := effect.effect_payload, dict)
        and (
            payload.get("effect_kind")
            in {FIGHTS_FIRST_EFFECT_KIND, CHARGE_FIGHTS_FIRST_EFFECT_KIND}
            or any(
                generic_rule_effect_payload_grants_ability(payload, ability=ability)
                for ability in ("fights_first", "infiltrators", "stealth")
            )
        )
        for effect in state.persisting_effects
    )


def _add(
    groups: dict[CoreAbilityFamily, list[AbilitySourceInstance]],
    unit: UnitInstance,
    family: CoreAbilityFamily,
    source_id: str,
    source_instance_id: str,
) -> None:
    source = AbilitySourceInstance(
        owner_id=unit.unit_instance_id,
        source_id=source_id,
        source_instance_id=source_instance_id,
        slot_id=f"core-grant:{family.value}",
        ability_id=f"core-{family.value.replace('_', '-')}",
    )
    values = groups.setdefault(family, [])
    if source not in values:
        values.append(source)
