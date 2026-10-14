"""Semantic identities for rules proved to belong to this exact attack subject."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.generic_rule_effect_targets import GenericAttackEffect
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def subject_rule_comparison(
    rules: dict[str, JsonValue],
    *,
    pool: RangedAttackPool,
    effects: tuple[GenericAttackEffect, ...],
    attacker_model_instance_id: str,
    source_component_unit_instance_id: str,
) -> dict[str, JsonValue]:
    """Normalize only gated THIS_MODEL subjects; raw proofs and runtime IDs remain."""
    compared = cast(dict[str, JsonValue], json.loads(canonical_json(rules)))
    modifier_ids: dict[str, str] = {}
    weapon_sources: dict[str, str] = {}
    characteristic_ids: dict[str, str] = {}
    reroll_sources: dict[tuple[str, int], tuple[dict[str, JsonValue], str]] = {}
    owned = tuple(
        effect
        for effect in effects
        if effect.role == "attacker"
        and effect.target_kind is RuleTargetKind.THIS_MODEL
        and effect.source_model_instance_id == attacker_model_instance_id
    )
    for effect in owned:
        template: dict[str, JsonValue] = {
            "role": effect.role,
            "source_id": effect.source_id,
            "rule_id": effect.rule_id,
            "rule_ir_hash": effect.rule_ir_hash,
            "clause_id": effect.clause_id,
            "effect_index": effect.effect_index,
            "effect_kind": effect.effect_kind.value,
            "target_kind": RuleTargetKind.THIS_MODEL.value,
            "parameters": effect.parameters,
            "conditions": list(effect.conditions),
            "subject": "physical-attack-subject",
        }
        if effect.effect_kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
            from warhammer40k_core.engine.native_gathering_weapon_source_rules import (
                owned_weapon_source_comparison,
            )

            weapon_sources.update(
                owned_weapon_source_comparison(
                    pool=pool,
                    effect=effect,
                    template={
                        **template,
                        "source_component_unit_instance_id": source_component_unit_instance_id,
                    },
                )
            )
        if effect.effect_kind is RuleEffectKind.MODIFY_DICE_ROLL:
            for roll_type in ("hit", "wound"):
                modifier_ids[
                    f"{effect.persisting_effect.effect_id}:{roll_type}:{effect.effect_index}"
                ] = (
                    "own-model-rule:"
                    + sha256(
                        canonical_json({**template, "roll_type": roll_type}).encode()
                    ).hexdigest()
                )
        if effect.effect_kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
            characteristic_ids[
                f"{effect.persisting_effect.effect_id}:skill:{effect.effect_index}"
            ] = "own-model-characteristic:" + sha256(canonical_json(template).encode()).hexdigest()
        if effect.effect_kind is RuleEffectKind.REROLL_PERMISSION:
            persisted = effect.persisting_effect
            expected: dict[str, JsonValue] = {
                "effect_kind": "generic_rule_execution",
                "rule_id": effect.rule_id,
                "source_id": effect.source_id,
                "rule_ir_hash": effect.rule_ir_hash,
                "clause_id": effect.clause_id,
                "effect_index": effect.effect_index,
                "effect_id": persisted.effect_id,
                "target_role": effect.role,
                "target_kind": RuleTargetKind.THIS_MODEL.value,
            }
            duration = {
                "source_rule_id": persisted.source_rule_id,
                "owner_player_id": persisted.owner_player_id,
                "target_unit_instance_ids": list(persisted.target_unit_instance_ids),
                "started_battle_round": persisted.started_battle_round,
                "started_phase": None
                if persisted.started_phase is None
                else persisted.started_phase.value,
                "expiration": persisted.expiration.to_payload(),
            }
            reroll_sources[(persisted.effect_id, effect.effect_index)] = (
                expected,
                "own-model-reroll:"
                + sha256(canonical_json({**template, "duration": duration}).encode()).hexdigest(),
            )
    for raw in cast(list[dict[str, JsonValue]], compared["generic_applicable_sources"]):
        if (
            raw["role"] == "attacker"
            and raw["target_kind"] == RuleTargetKind.THIS_MODEL.value
            and raw["source_model_instance_id"] == attacker_model_instance_id
        ):
            raw["source_model_instance_id"] = "physical-attack-subject"
    for raw in cast(list[dict[str, JsonValue]], compared["hit_modifiers"]):
        modifier = cast(dict[str, JsonValue], raw["modifier"])
        identifier = modifier["modifier_id"]
        matched_ids = characteristic_ids if raw["kind"] == "skill" else modifier_ids
        if isinstance(identifier, str) and identifier in matched_ids:
            modifier["modifier_id"] = matched_ids[identifier]
    for raw in cast(list[dict[str, JsonValue]], compared["wound_modifiers"]):
        identifier = raw["modifier_id"]
        if isinstance(identifier, str) and identifier in modifier_ids:
            raw["modifier_id"] = modifier_ids[identifier]
    for raw in cast(list[dict[str, JsonValue]], compared["ignore_permissions"]):
        permission = cast(dict[str, JsonValue], raw["permission"])
        context = permission["source_context"]
        if not isinstance(context, dict):
            continue
        if (
            context.get("source_kind") == "catalog"
            and context.get("source_target_kind") == RuleTargetKind.THIS_MODEL.value
            and context.get("source_model_instance_id") == attacker_model_instance_id
            and context.get("source_unit_instance_id") == source_component_unit_instance_id
            and context.get("eligible_source_model_ids") == [attacker_model_instance_id]
            and permission["permission_id"]
            == (
                f"{permission['record_id']}:{permission['clause_id']}:"
                f"{source_component_unit_instance_id}:{attacker_model_instance_id}:modifier-ignore"
            )
        ):
            context["source_model_instance_id"] = "physical-attack-subject"
            context["eligible_source_model_ids"] = ["physical-attack-subject"]
            template = {key: value for key, value in permission.items() if key != "permission_id"}
            permission["permission_id"] = (
                "own-model-permission:" + sha256(canonical_json(template).encode()).hexdigest()
            )
    for family in ("hit_rerolls", "wound_rerolls"):
        for raw in cast(list[dict[str, JsonValue]], compared[family]):
            source = cast(dict[str, JsonValue], raw["source_payload"])
            effect_id, index = source.get("effect_id"), source.get("effect_index")
            if not isinstance(effect_id, str) or type(index) is not int:
                continue
            matched = reroll_sources.get((effect_id, index))
            if matched is not None and all(source.get(k) == v for k, v in matched[0].items()):
                source["effect_id"] = matched[1]
    from warhammer40k_core.engine.native_gathering_characteristic_rules import (
        compare_characteristic_descriptors,
    )

    compare_characteristic_descriptors(compared, modifier_ids=characteristic_ids)
    signature = cast(dict[str, JsonValue], compared["semantic_signature"])
    signature["weapon_rule_tokens"] = cast(
        list[JsonValue],
        sorted(
            weapon_sources.get(token, token)
            for token in cast(list[str], signature["weapon_rule_tokens"])
        ),
    )
    for family in (
        "generic_applicable_sources",
        "hit_modifiers",
        "wound_modifiers",
        "ignore_permissions",
        "hit_rerolls",
        "wound_rerolls",
    ):
        compared[family] = sorted(cast(list[JsonValue], compared[family]), key=canonical_json)
    return compared
