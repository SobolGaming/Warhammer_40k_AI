"""One model-complete Stealth query for native, granted and retained ability sources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    conditional_leader_grant_effect_applies,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.unit_abilities import descriptor_is_stealth
from warhammer40k_core.engine.unit_split_views import split_effect_predecessor_ids
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stealth_2026_09 import (
    STEALTH_SOURCE_ID as STEALTH_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def native_stealth_model_sources(view: RulesUnitView) -> dict[str, tuple[str, ...]]:
    sources: dict[str, tuple[str, ...]] = {}
    for component in view.components:
        descriptor_ids = tuple(
            ability.source_id
            for ability in component.unit.datasheet_abilities
            if descriptor_is_stealth(ability)
        )
        for model in component.unit.own_models:
            if not model.is_alive and model.model_instance_id not in view.retained_model_ids:
                continue
            ids = descriptor_ids
            if "STEALTH" in model.keywords:
                ids = (*ids, *model.keyword_assignment.source_ids)
            sources[model.model_instance_id] = tuple(sorted(set(ids)))
    return sources


def rules_unit_has_native_stealth(view: RulesUnitView) -> bool:
    sources = native_stealth_model_sources(view)
    return bool(sources) and all(sources.values())


def rules_unit_stealth_sources(
    *,
    state: GameState,
    target_unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> JsonValue:
    """Return complete source commitments only when every present model has Stealth."""
    view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    native = native_stealth_model_sources(view)
    covered = {model_id for model_id, sources in native.items() if sources}
    commitments: list[JsonValue] = [
        {"model_id": model_id, "source_ids": list(sources)}
        for model_id, sources in sorted(native.items())
        if sources
    ]
    for application in rules_unit_effect_applications(state, view.unit_instance_id):
        effect = application.effect
        payload = effect.effect_payload
        if not isinstance(payload, dict) or not generic_rule_effect_payload_grants_ability(
            payload, ability="stealth"
        ):
            continue
        effect_target = payload.get("target")
        if payload.get("descriptor_id") == CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID:
            if not conditional_leader_grant_effect_applies(
                state=state, effect=effect, rules_unit_instance_id=view.unit_instance_id
            ):
                continue
            ids = set(native)
        elif isinstance(effect_target, dict) and effect_target.get("kind") == "this_model":
            context_payload = payload.get("context")
            if not isinstance(context_payload, dict):
                raise GameLifecycleError("A model ability grant requires source context.")
            source_model_id = context_payload.get("source_model_instance_id")
            if type(source_model_id) is not str:
                raise GameLifecycleError("A model ability grant requires a source model ID.")
            ids = {source_model_id} & set(native)
        elif application.unit_instance_id == view.unit_instance_id:
            ids = set(native)
        else:
            component_ids = {
                component.unit.unit_instance_id
                for component in view.components
                if any(
                    effect.applies_to_unit(predecessor)
                    for predecessor in split_effect_predecessor_ids(
                        armies=tuple(state.army_definitions),
                        unit_instance_id=component.unit.unit_instance_id,
                    )
                )
            }
            ids = {
                model_id
                for model_id in native
                if view.component_unit_id_for_model(model_id) in component_ids
            }
        covered.update(ids)
        commitments.append(
            {
                "effect": validate_json_value(effect.to_payload()),
                "model_ids": validate_json_value(sorted(ids)),
            }
        )
    if runtime_modifier_registry is not None:
        context = ModelAbilityGrantContext(state, view)
        for binding in runtime_modifier_registry.model_ability_grant_bindings:
            if binding.ability_id != "core-stealth":
                continue
            grant_ids = binding.model_ids(context)
            if grant_ids:
                covered.update(grant_ids)
                commitments.append(
                    {
                        "binding_id": binding.modifier_id,
                        "source_id": binding.source_id,
                        "model_ids": list(grant_ids),
                    }
                )
    if not native or covered != set(native):
        return None
    return {"source_rule_id": STEALTH_SOURCE_ID, "sources": commitments}
