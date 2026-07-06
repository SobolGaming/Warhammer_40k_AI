from __future__ import annotations

from typing import Protocol, cast

from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleStratagemCostModifierAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierContext
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)

_COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID = (
    f"{court_ir.SOURCE_PACKAGE_ID}:"
    f"{court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID}:source-text"
)


class _CourtOfThePhoenicianRuleModule(Protocol):
    MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID: str

    def master_of_the_pageant_command_point_cost_modifier(
        self,
        context: StratagemCostModifierContext,
    ) -> int: ...


def emperors_children_court_of_the_phoenician_stratagem_cost_modifier_abilities() -> tuple[
    GenericRuleStratagemCostModifierAbility, ...
]:
    return (
        GenericRuleStratagemCostModifierAbility(
            ability_id=court_ir.MASTER_OF_THE_PAGEANT_STRATAGEM_COST_REDUCTION_ABILITY,
            coverage_descriptor_id=court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID,
            modifier_id_builder=_master_of_the_pageant_cost_modifier_id,
            context_predicate=_master_of_the_pageant_context_predicate,
            modifier_builder=_master_of_the_pageant_cost_modifier,
        ),
    )


def _court_of_the_phoenician_rule() -> _CourtOfThePhoenicianRuleModule:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children.detachments.court_of_the_phoenician import (  # noqa: E501
        rule,
    )

    return cast(_CourtOfThePhoenicianRuleModule, rule)


def _master_of_the_pageant_context_predicate(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Master of the Pageant cost modifier requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Master of the Pageant cost modifier requires source.")
    return True


def _master_of_the_pageant_cost_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Master of the Pageant modifier ID requires source.")
    return _court_of_the_phoenician_rule().MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID


def _master_of_the_pageant_cost_modifier(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> int:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Master of the Pageant modifier requires source.")
    return _court_of_the_phoenician_rule().master_of_the_pageant_command_point_cost_modifier(
        context
    )
