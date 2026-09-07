from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.aura_applications import (
    non_stacking_aura_applications,
    persisting_effects_for_lineage,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.tracked_target_state import attached_rules_unit_ids
from warhammer40k_core.engine.unit_split_views import split_effect_predecessor_ids

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_state import StartingStrengthRecord


def known_effect_target_unit_ids(
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
) -> set[str]:
    """Validate historical targets against authenticated current and source inventories."""
    return (
        {unit.unit_instance_id for army in army_definitions for unit in army.units}
        | attached_rules_unit_ids(tuple(army_definitions))
        | {record.unit_instance_id for record in starting_strength_records}
        | {
            unit.unit_instance_id
            for army in army_definitions
            for record in army.unit_splits
            for unit in record.source_units
        }
    )


@dataclass(frozen=True, slots=True)
class RulesUnitEffectApplication:
    unit_instance_id: str
    effect: PersistingEffect
    matched_target_unit_instance_ids: tuple[str, ...]


def rules_unit_effect_applications(
    state: GameState, unit_instance_id: str
) -> tuple[RulesUnitEffectApplication, ...]:
    """Bind current applicability to unchanged effect provenance, once per instance."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Rules-unit effect lookup requires GameState.")
    return rules_unit_effect_applications_from_inventory(
        armies=tuple(state.army_definitions),
        effects=tuple(state.persisting_effects),
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id),
    )


def rules_unit_effect_applications_from_inventory(
    *,
    armies: tuple[ArmyDefinition, ...],
    effects: tuple[PersistingEffect, ...],
    rules_unit: RulesUnitView,
) -> tuple[RulesUnitEffectApplication, ...]:
    """Use the same immutable target lineage and Aura policy for any authenticated boundary."""
    identity_ids = tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )
    candidates = non_stacking_aura_applications(
        tuple(
            (identity_id, effect)
            for identity_id in identity_ids
            for effect in persisting_effects_for_lineage(
                list(effects),
                split_effect_predecessor_ids(armies=armies, unit_instance_id=identity_id),
            )
        )
    )
    applications: list[RulesUnitEffectApplication] = []
    seen: set[str] = set()
    for current_id, effect in candidates:
        predecessors = split_effect_predecessor_ids(armies=armies, unit_instance_id=current_id)
        matched = tuple(target for target in predecessors if effect.applies_to_unit(target))
        if not matched:
            raise GameLifecycleError("Effect application lacks authenticated target membership.")
        if effect.effect_id not in seen:
            applications.append(RulesUnitEffectApplication(current_id, effect, matched))
            seen.add(effect.effect_id)
    return tuple(applications)


def rules_unit_persisting_effects(
    state: GameState,
    unit_instance_id: str,
) -> tuple[tuple[str, PersistingEffect], ...]:
    """Return effects keyed by every current physical/rules-unit identity."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Rules-unit effect lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    identity_ids = tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )
    return non_stacking_aura_applications(
        tuple(
            (identity_id, effect)
            for identity_id in identity_ids
            for effect in state.persisting_effects_for_unit(identity_id)
        )
    )
