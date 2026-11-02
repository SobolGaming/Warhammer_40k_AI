"""Source-linked ranged Cover for models in a unit led by the conferring model."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine.catalog_cover_support import (
    clause_is_leading_cover as clause_is_leading_cover,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.model_ability_grants import (
    ModelAbilityGrantBinding,
    ModelAbilityGrantContext,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
        CatalogDatasheetClauseSource,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def catalog_cover_grant_binding(source: CatalogDatasheetClauseSource) -> ModelAbilityGrantBinding:
    return ModelAbilityGrantBinding(
        modifier_id=f"{source.binding_id}:model-cover-grant",
        source_id=source.rule_ir.source_id,
        ability_id="core-benefit-of-cover",
        handler=_grant_handler(source),
    )


def _grant_handler(
    source: CatalogDatasheetClauseSource,
) -> Callable[[ModelAbilityGrantContext], tuple[str, ...]]:
    from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
        current_effect_target_model_ids,
        source_applies_to_rules_unit,
        source_currently_leading_rules_unit,
    )

    def handler(context: ModelAbilityGrantContext) -> tuple[str, ...]:
        if not source_applies_to_rules_unit(
            source=source, context_unit_id=context.target.unit_instance_id, state=context.state
        ) or not source_currently_leading_rules_unit(
            source=source, context_unit_id=context.target.unit_instance_id, state=context.state
        ):
            return ()
        return current_effect_target_model_ids(state=context.state, source=source)

    return handler


def catalog_cover_inventory(
    *,
    state: GameState,
    target_unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> dict[str, JsonValue]:
    """Commit the native grants without altering unrelated historical Cover witnesses."""
    if runtime_modifier_registry is None:
        return {}
    view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    present = {
        model.model_instance_id
        for model in view.own_models
        if model.is_alive or model.model_instance_id in view.retained_model_ids
    }
    covered: set[str] = set()
    commitments: list[JsonValue] = []
    context = ModelAbilityGrantContext(state, view)
    for binding in runtime_modifier_registry.model_ability_grant_bindings:
        if binding.ability_id != "core-benefit-of-cover":
            continue
        ids = binding.model_ids(context)
        if ids:
            covered.update(ids)
            commitments.append(
                {
                    "binding_id": binding.modifier_id,
                    "source_id": binding.source_id,
                    "model_ids": list(ids),
                }
            )
    if not present or covered != present:
        return {}
    return {"catalog_cover": commitments}
