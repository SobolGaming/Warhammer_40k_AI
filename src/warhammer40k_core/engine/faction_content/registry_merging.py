from __future__ import annotations

from warhammer40k_core.engine.abilities import (
    AbilityHandlerBinding,
    AbilityHandlerRegistry,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerBinding,
    StratagemHandlerRegistry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import RuleExecutionRegistry, RuleRuntimeBinding


def merged_ability_registry(
    base: AbilityHandlerRegistry | None,
    contribution_bindings: tuple[AbilityHandlerBinding, ...],
) -> AbilityHandlerRegistry:
    resolved_base = default_ability_handler_registry() if base is None else base
    if type(resolved_base) is not AbilityHandlerRegistry:
        raise GameLifecycleError("Runtime content base ability registry is invalid.")
    return AbilityHandlerRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )


def merged_stratagem_registry(
    base: StratagemHandlerRegistry | None,
    contribution_bindings: tuple[StratagemHandlerBinding, ...],
) -> StratagemHandlerRegistry:
    resolved_base = StratagemHandlerRegistry.empty() if base is None else base
    if type(resolved_base) is not StratagemHandlerRegistry:
        raise GameLifecycleError("Runtime content base Stratagem registry is invalid.")
    return StratagemHandlerRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )


def merged_rule_registry(
    base: RuleExecutionRegistry | None,
    contribution_bindings: tuple[RuleRuntimeBinding, ...],
) -> RuleExecutionRegistry:
    resolved_base = RuleExecutionRegistry.empty() if base is None else base
    if type(resolved_base) is not RuleExecutionRegistry:
        raise GameLifecycleError("Runtime content base rule registry is invalid.")
    return RuleExecutionRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )
