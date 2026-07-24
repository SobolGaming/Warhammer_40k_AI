from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
)
from warhammer40k_core.engine.stratagem_phase_use_exceptions import (
    phase_use_exception_effect_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    july_faction_packs_2026_07,
)

CONTRIBUTION_ID = "warhammer_40000_11th:thousand_sons:defiler:july_2026_candidate"


def runtime_contribution() -> RuntimeContentContribution:
    artifact = july_faction_packs_2026_07.thousand_sons_defiler()
    matching_records = tuple(
        record
        for record in eleventh_edition_core_stratagem_catalog_records()
        if record.definition.stratagem_id == artifact.counteroffensive_stratagem_id
    )
    if len(matching_records) != 1:
        raise GameLifecycleError(
            "July Thousand Sons Defiler requires one core Counteroffensive record."
        )
    core_record = matching_records[0]
    candidate_record = replace(
        core_record,
        definition=replace(
            core_record.definition,
            effect_payload=phase_use_exception_effect_payload(
                source_ability_id=artifact.source_ability_id,
                source_id=artifact.runtime_consumer_ids[0],
                eligible_datasheet_ids=(artifact.datasheet_id,),
            ),
        ),
    )
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(candidate_record,),
        stratagem_cost_modifier_bindings=(
            StratagemCostModifierBinding(
                modifier_id=artifact.runtime_consumer_ids[1],
                source_id=artifact.source_ability_id,
                handler=_destroyer_of_futures_counteroffensive_cost,
            ),
        ),
    )


def _destroyer_of_futures_counteroffensive_cost(
    context: StratagemCostModifierContext,
) -> int:
    artifact = july_faction_packs_2026_07.thousand_sons_defiler()
    target_id = (
        None if context.target_binding is None else context.target_binding.target_unit_instance_id
    )
    if (
        context.definition.stratagem_id != artifact.counteroffensive_stratagem_id
        or target_id is None
    ):
        return context.current_command_point_cost
    for army in context.state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == target_id:
                if unit.datasheet_id == artifact.datasheet_id:
                    return context.current_command_point_cost - 1
                return context.current_command_point_cost
    return context.current_command_point_cost
