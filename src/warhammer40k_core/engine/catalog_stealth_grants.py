"""Catalog RuleIR providers of Stealth model grants; Cover remains Core-owned."""

from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_effect_target_model_ids,
    current_source_model_ids,
    source_applies_to_rules_unit,
)
from warhammer40k_core.engine.model_ability_grants import (
    ModelAbilityGrantBinding,
    ModelAbilityGrantContext,
)
from warhammer40k_core.engine.rule_aura_resolution import aura_affected_unit_ids


def catalog_stealth_grant_bindings(
    *,
    aura_sources: tuple[CatalogDatasheetClauseSource, ...],
    self_sources: tuple[CatalogDatasheetClauseSource, ...],
) -> tuple[ModelAbilityGrantBinding, ...]:
    return tuple(
        ModelAbilityGrantBinding(
            modifier_id=f"{source.binding_id}:model-ability-grant",
            source_id=source.rule_ir.source_id,
            ability_id="core-stealth",
            handler=_grant_handler(source, aura=aura),
        )
        for sources, aura in ((aura_sources, True), (self_sources, False))
        for source in sources
    )


def _grant_handler(
    source: CatalogDatasheetClauseSource, *, aura: bool
) -> Callable[[ModelAbilityGrantContext], tuple[str, ...]]:
    def handler(context: ModelAbilityGrantContext) -> tuple[str, ...]:
        if aura:
            if any(
                context.target.unit_instance_id
                in aura_affected_unit_ids(
                    clause=source.clause,
                    state=context.state,
                    source_unit_instance_id=source.unit.unit_instance_id,
                    source_model_instance_id=model_id,
                )
                for model_id in current_source_model_ids(state=context.state, source=source)
            ):
                return tuple(
                    model.model_instance_id
                    for model in context.target.own_models
                    if model.is_alive
                    or model.model_instance_id in context.target.retained_model_ids
                )
            return ()
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.target.unit_instance_id,
            state=context.state,
        ):
            return ()
        return current_effect_target_model_ids(state=context.state, source=source)

    return handler
