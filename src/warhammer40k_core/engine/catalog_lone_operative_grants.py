"""Conditional Lone Operative grants expose the same sources as their consumer."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    source_applies_to_rules_unit,
)
from warhammer40k_core.engine.model_ability_grants import (
    ModelAbilityGrantBinding,
    ModelAbilityGrantContext,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    TargetRestriction,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def lone_operative_grant_binding(source: CatalogDatasheetClauseSource) -> ModelAbilityGrantBinding:
    return ModelAbilityGrantBinding(
        modifier_id=f"{source.binding_id}:core-lone-operative",
        source_id=source.rule_ir.source_id,
        ability_id="core-lone-operative",
        handler=_handler(source),
    )


def _handler(
    source: CatalogDatasheetClauseSource,
) -> Callable[[ModelAbilityGrantContext], tuple[str, ...]]:
    def handler(context: ModelAbilityGrantContext) -> tuple[str, ...]:
        from warhammer40k_core.engine.catalog_datasheet_rule_runtime import (
            _friendly_keyworded_unit_within,
        )

        if not source_applies_to_rules_unit(
            source=source, context_unit_id=context.target.unit_instance_id, state=context.state
        ) or not _friendly_keyworded_unit_within(source=source, state=context.state):
            return ()
        return tuple(
            model.model_instance_id
            for model in context.target.own_models
            if model.is_alive or model.model_instance_id in context.target.retained_model_ids
        )

    return handler


def selected_lone_operative_grant_applies(
    *, state: GameState, target_unit_id: str, source: CatalogDatasheetClauseSource
) -> bool:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    active = False
    for component in view.living_components:
        choices = tuple(
            choice
            for choice in component.unit.core_ability_selections
            if choice.family is CoreAbilityFamily.LONE_OPERATIVE
        )
        if not choices:
            if any(
                ability.core_family is CoreAbilityFamily.LONE_OPERATIVE
                for ability in component.unit.datasheet_abilities
            ):
                raise GameLifecycleError(
                    "Duplicated Lone Operative requires controlling-player selection."
                )
            active = True
        elif (
            choices[0].runtime_source is not None
            and choices[0].runtime_source.source_instance_id
            == f"{source.binding_id}:core-lone-operative"
        ):
            active = True
    return active


def lone_operative_restriction_handler(
    sources: tuple[CatalogDatasheetClauseSource, ...],
) -> Callable[[ShootingTargetRestrictionContext], TargetRestriction | None]:
    from warhammer40k_core.engine.catalog_datasheet_rule_runtime import (
        _friendly_keyworded_unit_within,
        _rules_units_within,
    )
    from warhammer40k_core.engine.catalog_datasheet_rule_support import (
        CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    )

    def handler(context: ShootingTargetRestrictionContext) -> TargetRestriction | None:
        for source in sources:
            if not source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.target_unit_instance_id,
                state=context.state,
            ) or not _friendly_keyworded_unit_within(source=source, state=context.state):
                continue
            if not selected_lone_operative_grant_applies(
                state=context.state,
                target_unit_id=context.target_unit_instance_id,
                source=source,
            ):
                continue
            if _rules_units_within(
                context.state,
                context.attacking_unit_instance_id,
                context.target_unit_instance_id,
                12,
                attacker_model_instance_id=context.attacker_model_instance_id,
            ):
                return None
            return TargetRestriction(
                hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                violation_code="conditional_lone_operative_range",
                message=('Target has Lone Operative and the attacking model is not within 12".'),
                replay_payload={
                    "consumer_id": CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "target_unit_instance_id": context.target_unit_instance_id,
                },
            )
        return None

    return handler
