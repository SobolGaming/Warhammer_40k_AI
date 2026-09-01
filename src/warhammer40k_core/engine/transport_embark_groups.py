from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies


def embarking_rules_unit_placement(
    *,
    scenario: BattlefieldScenario,
    selected_unit_placement: UnitPlacement,
) -> tuple[RulesUnitView, RulesUnitPlacement]:
    """Resolve one selected physical component to its complete current rules unit."""
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Embark rules-unit resolution requires BattlefieldScenario.")
    if type(selected_unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Embark rules-unit resolution requires UnitPlacement.")
    rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=selected_unit_placement.unit_instance_id,
    )
    battlefield_grouped = RulesUnitPlacement.from_battlefield(
        view=rules_unit,
        battlefield_state=scenario.battlefield_state,
    )
    if (
        selected_unit_placement.unit_instance_id
        not in battlefield_grouped.component_unit_instance_ids
    ):
        raise GameLifecycleError("Embark selection must identify a living rules-unit component.")
    grouped = RulesUnitPlacement(
        rules_unit_instance_id=battlefield_grouped.rules_unit_instance_id,
        component_unit_placements=tuple(
            selected_unit_placement
            if placement.unit_instance_id == selected_unit_placement.unit_instance_id
            else placement
            for placement in battlefield_grouped.component_unit_placements
        ),
    )
    grouped.validate_for_view(rules_unit)
    return rules_unit, grouped


def embark_transition_batch_for_rules_unit(
    *,
    rules_unit_placement: RulesUnitPlacement,
    transport_unit_instance_id: str,
    source_rule_id: str,
) -> BattlefieldTransitionBatch:
    if type(rules_unit_placement) is not RulesUnitPlacement:
        raise GameLifecycleError("Embark transition requires RulesUnitPlacement.")
    return BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=model_placement.model_instance_id,
                removal_kind=BattlefieldRemovalKind.EMBARK,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_rule_id=source_rule_id,
                source_event_id=None,
                destination_id=transport_unit_instance_id,
            )
            for model_placement in rules_unit_placement.model_placements
        )
    )


def cargo_model_count(
    *,
    scenario: BattlefieldScenario,
    embarked_unit_instance_ids: tuple[str, ...],
) -> int:
    units = {unit.unit_instance_id: unit for army in scenario.armies for unit in army.units}
    count = 0
    for unit_id in embarked_unit_instance_ids:
        unit = units.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Transport cargo references an unknown embarked unit.")
        count += sum(model.is_alive for model in unit.own_models)
    return count


def remove_embarking_rules_unit_from_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    transition_batch: BattlefieldTransitionBatch,
) -> BattlefieldRuntimeState:
    """Apply one accepted Embark transition as complete physical-unit removals."""
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Embark removal requires BattlefieldRuntimeState.")
    if type(transition_batch) is not BattlefieldTransitionBatch:
        raise GameLifecycleError("Embark removal requires BattlefieldTransitionBatch.")
    removal_model_ids = {removal.model_instance_id for removal in transition_batch.removals}
    if not removal_model_ids or any(
        removal.removal_kind is not BattlefieldRemovalKind.EMBARK
        for removal in transition_batch.removals
    ):
        raise GameLifecycleError("Embark transition must contain only Embark removals.")

    removed_component_ids: list[str] = []
    accounted_model_ids: set[str] = set()
    for placed_army in battlefield_state.placed_armies:
        for placement in placed_army.unit_placements:
            component_model_ids = {
                model_placement.model_instance_id for model_placement in placement.model_placements
            }
            overlap = component_model_ids.intersection(removal_model_ids)
            if overlap and overlap != component_model_ids:
                raise GameLifecycleError(
                    "Embark transition must remove every placed model in each component."
                )
            if overlap:
                removed_component_ids.append(placement.unit_instance_id)
                accounted_model_ids.update(overlap)
    if accounted_model_ids != removal_model_ids:
        raise GameLifecycleError("Embark transition removal-model identity drift.")

    updated = battlefield_state
    for component_id in sorted(removed_component_ids):
        updated = updated.without_unit_placement(component_id)
    return updated
