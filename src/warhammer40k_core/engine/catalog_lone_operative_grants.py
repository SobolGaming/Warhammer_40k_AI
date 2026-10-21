"""Conditional Lone Operative grants expose the same sources as their consumer."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_effect_target_model_ids,
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
from warhammer40k_core.engine.unit_abilities import lone_operative_profile_for_unit

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
        return current_effect_target_model_ids(state=context.state, source=source)

    return handler


def selected_lone_operative_grant_applies(
    *, state: GameState, target_unit_id: str, source: CatalogDatasheetClauseSource
) -> bool:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    recipients = set(current_effect_target_model_ids(state=state, source=source))
    active = False
    for component in view.rules_present_components:
        if not recipients.intersection(component.unit.own_model_ids()):
            continue
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
        _rules_units_within,
    )
    from warhammer40k_core.engine.catalog_datasheet_rule_support import (
        CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    )

    def handler(context: ShootingTargetRestrictionContext) -> TargetRestriction | None:
        from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext
        from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

        view = rules_unit_view_by_id(
            state=context.state, unit_instance_id=context.target_unit_instance_id
        )
        required = {
            model.model_instance_id
            for model in view.own_models
            if model.is_alive or model.model_instance_id in view.retained_model_ids
        }
        if not required:
            return None
        covered: set[str] = set()
        ranges: list[float] = []
        for component in view.rules_present_components:
            profile = lone_operative_profile_for_unit(component.unit)
            if profile is not None:
                covered.update(required.intersection(component.unit.own_model_ids()))
                ranges.append(profile.range_inches)
        applicable: list[CatalogDatasheetClauseSource] = []
        for source in sources:
            granted = _handler(source)(ModelAbilityGrantContext(context.state, view))
            if not granted:
                continue
            if not selected_lone_operative_grant_applies(
                state=context.state,
                target_unit_id=context.target_unit_instance_id,
                source=source,
            ):
                continue
            covered.update(granted)
            ranges.append(12.0)
            applicable.append(source)
        # 19.04/FAQ64 preserves each model's recipient scope. The attached
        # Lone Operative consumer needs every currently present model covered.
        if not applicable or not required.issubset(covered):
            return None
        max_range = max(ranges)
        if _rules_units_within(
            context.state,
            context.attacking_unit_instance_id,
            context.target_unit_instance_id,
            max_range,
            attacker_model_instance_id=context.attacker_model_instance_id,
        ):
            return None
        source = applicable[0]
        return TargetRestriction(
            hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
            source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
            violation_code="conditional_lone_operative_range",
            message=(
                f'Target has Lone Operative and the attacking model is not within {max_range:g}".'
            ),
            replay_payload={
                "consumer_id": CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.rule_ir.source_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
            },
        )

    return handler
