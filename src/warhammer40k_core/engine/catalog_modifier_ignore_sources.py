"""Prospective source identity, separate from occurrence permission evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_modifier_ignore import CatalogModifierIgnorePermission
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
    from warhammer40k_core.engine.rules_units import RulesUnitView


@dataclass(frozen=True, slots=True)
class ModifierIgnoreSourceTemplate:
    raw_payload: dict[str, JsonValue]
    comparison_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ModifierIgnoreGatheringSources:
    catalog_permissions: tuple[CatalogModifierIgnorePermission, ...]
    persisted_source_templates: tuple[ModifierIgnoreSourceTemplate, ...]


def explicit_modifier_ignore_kinds_for_gathering(
    parameters: dict[str, JsonValue],
) -> tuple[ModifierIgnoreKind, ...] | None:
    """Only a complete explicit known set proves kind irrelevance; no grammar grant."""
    values = parameters.get("modifier_kinds")
    known = {kind.value for kind in ModifierIgnoreKind}
    if (
        not isinstance(values, list)
        or not values
        or any(type(value) is not str or value not in known for value in values)
    ):
        return None
    tokens = cast(list[str], values)
    if len(set(tokens)) != len(tokens):
        return None
    return tuple(ModifierIgnoreKind(value) for value in tokens)


def persisted_modifier_ignore_source_templates(
    *,
    state: GameState,
    view: RulesUnitView,
    current_ids: tuple[str, ...],
    model_id: str | None,
    kind: ModifierIgnoreKind,
    subject_context: dict[str, JsonValue],
    context: ModifierPermissionAttackContext,
) -> tuple[ModifierIgnoreSourceTemplate, ...]:
    """Bind each matched source to its real beneficiary, owner and current lifetime.

    Parameters and residual conditions remain source data. This does not decode
    selection grammar, validate occurrence restrictions, or grant an ignore choice.
    """
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_effect_gathering_context_applies,
        generic_matching_unit_effect_applications,
    )
    from warhammer40k_core.engine.generic_rule_effect_targets import generic_effect_role_applies
    from warhammer40k_core.engine.rules_unit_effects import (
        rules_unit_effect_applications_from_inventory,
    )

    candidates = generic_matching_unit_effect_applications(
        applications=rules_unit_effect_applications_from_inventory(
            armies=tuple(state.army_definitions),
            effects=tuple(state.persisting_effects),
            rules_unit=view,
        ),
        effect_kind=RuleEffectKind.GRANT_ABILITY,
        role=context.subject_role,
        application_filter=lambda effect, _unit_id: (
            effect.parameters.get("ability") == "modifier_ignore_permission"
        ),
    )
    result: list[ModifierIgnoreSourceTemplate] = []
    subject_model = current_ids[0] if model_id is None and len(current_ids) == 1 else model_id
    for effect in candidates:
        explicit_kinds = explicit_modifier_ignore_kinds_for_gathering(effect.parameters)
        if explicit_kinds is not None and kind not in explicit_kinds:
            continue
        if effect.target_kind is RuleTargetKind.THIS_MODEL:
            if effect.source_model_instance_id not in current_ids:
                continue
            if effect.source_model_instance_id != subject_model:
                continue
        if not generic_effect_role_applies(
            effect=effect,
            role=context.subject_role,
            attacking_unit_instance_id=(
                effect.effective_target_unit_instance_ids[0]
                if context.subject_role == "attacker"
                else context.attacking_unit_instance_id
            ),
            target_unit_instance_id=(
                effect.effective_target_unit_instance_ids[0]
                if context.subject_role == "target"
                else context.target_unit_instance_id
            ),
            legacy_attacker_role_allowed=lambda _effect: True,
            legacy_target_role_allowed=lambda _effect: True,
        ):
            continue
        if not generic_effect_gathering_context_applies(
            state=state,
            effect=effect,
            attacking_unit_instance_id=context.attacking_unit_instance_id,
            attacker_model_instance_id=context.attacker_model_instance_id,
            target_unit_instance_id=context.target_unit_instance_id,
            source_phase=context.source_phase,
            weapon_profile=context.weapon_profile,
            attack_strength=context.attack_strength,
            target_toughness=context.target_toughness,
            subject_model_instance_id=subject_model,
        ):
            continue
        persisted = effect.persisting_effect
        if persisted.source_rule_id != effect.source_id:
            raise GameLifecycleError("Persisted modifier-ignore source identity drift.")
        source_model = effect.source_model_instance_id
        source_component = (
            view.component_unit_id_for_model(source_model)
            if source_model is not None and source_model in current_ids
            else None
        )
        source: dict[str, JsonValue] = {
            "role": effect.role,
            "source_id": effect.source_id,
            "rule_id": effect.rule_id,
            "rule_ir_hash": effect.rule_ir_hash,
            "clause_id": effect.clause_id,
            "effect_index": effect.effect_index,
            "effect_kind": effect.effect_kind.value,
            "target_kind": None if effect.target_kind is None else effect.target_kind.value,
            "parameters": effect.parameters,
            "conditions": cast(list[JsonValue], list(effect.conditions)),
            "source_model_instance_id": effect.source_model_instance_id,
            "source_component_unit_instance_id": source_component,
            "effective_target_unit_instance_ids": list(effect.effective_target_unit_instance_ids),
        }
        lifetime: dict[str, JsonValue] = {
            "source_rule_id": persisted.source_rule_id,
            "owner_player_id": persisted.owner_player_id,
            "target_unit_instance_ids": list(persisted.target_unit_instance_ids),
            "started_battle_round": persisted.started_battle_round,
            "started_phase": None
            if persisted.started_phase is None
            else persisted.started_phase.value,
            "expiration": validate_json_value(persisted.expiration.to_payload()),
        }
        compared = cast(
            dict[str, JsonValue],
            json.loads(
                canonical_json(
                    {
                        "kind": kind.value,
                        "subject": subject_context,
                        "source": source,
                        "persisting_owner_and_lifetime": lifetime,
                        "effect_id": persisted.effect_id,
                    }
                )
            ),
        )
        # Application identity is relative only after the real attacker subject
        # and its equipped profile have passed the shared lookup. Source identity
        # is independent: a unit or foreign source retains its actual owner/ID.
        if context.subject_role == "attacker":
            semantic_subject = cast(dict[str, JsonValue], compared["subject"])
            for field in (
                "subject_model_instance_id",
                "subject_weapon_profile_id",
                "subject_component_unit_instance_id",
            ):
                semantic_subject.pop(field)
        # Only a current, physically bound own-model source has a relative identity.
        # Unit, foreign, unmatched and unknown identities retain their real effect ID.
        if (
            context.subject_role == "attacker"
            and effect.role == "attacker"
            and effect.target_kind is RuleTargetKind.THIS_MODEL
            and effect.source_model_instance_id == context.attacker_model_instance_id == model_id
            and persisted.owner_player_id == view.owner_player_id
            and source_component is not None
        ):
            semantic_source = cast(dict[str, JsonValue], compared["source"])
            semantic_source["source_model_instance_id"] = "physical-attack-subject"
            compared.pop("effect_id")
            compared["effect_id"] = (
                "own-model-ignore-source:" + sha256(canonical_json(compared).encode()).hexdigest()
            )
        raw: dict[str, JsonValue] = {
            "kind": kind.value,
            "subject": subject_context,
            "source": source,
            "persisting_effect": validate_json_value(persisted.to_payload()),
        }
        result.append(ModifierIgnoreSourceTemplate(raw, compared))
    return tuple(sorted(result, key=lambda row: canonical_json(row.comparison_payload)))
