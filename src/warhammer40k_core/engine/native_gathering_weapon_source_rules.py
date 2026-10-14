"""Compare only exact own-model grant occurrences proved by their native producer."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json

if TYPE_CHECKING:
    from warhammer40k_core.engine.generic_rule_effect_targets import GenericAttackEffect
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def owned_weapon_source_comparison(
    *,
    pool: RangedAttackPool,
    effect: GenericAttackEffect,
    template: dict[str, JsonValue],
) -> dict[str, str]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import generic_rule_modifier_source_id
    from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
        rule_ir_weapon_ability_granted_profile,
    )

    context = pool.weapon_selection_context
    if context is None:
        return {}
    source_instance_id = f"{effect.persisting_effect.effect_id}:{effect.effect_index}"
    source_id = generic_rule_modifier_source_id(effect)
    generated = rule_ir_weapon_ability_granted_profile(
        profile=pool.weapon_profile,
        parameters=effect.parameters,
        source_id=source_id,
        source_instance_id=source_instance_id,
    )
    offered_sources = {
        source.instance_id: source for _, group in context.instance_groups() for source in group
    }
    replacements: dict[str, str] = {}
    for source in generated.ability_sources:
        if (
            source.source_id != source_id
            or source.source_instance_id != source_instance_id
            or offered_sources.get(source.instance_id) != source
        ):
            continue
        # Use the same physical-owner normalization as the frozen raw signature.
        owner = (
            "selected-physical-weapon"
            if source.owner_id == pool.weapon_instance_id
            else source.owner_id
        )
        raw: dict[str, JsonValue] = {
            "owner_id": owner,
            "source_id": source.source_id,
            "source_instance_id": source.source_instance_id,
            "slot_id": source.slot_id,
            "ability_id": source.ability_id,
        }
        persisted = effect.persisting_effect
        duration: dict[str, JsonValue] = {
            "source_rule_id": persisted.source_rule_id,
            "owner_player_id": persisted.owner_player_id,
            "target_unit_instance_ids": list(persisted.target_unit_instance_ids),
            "started_battle_round": persisted.started_battle_round,
            "started_phase": None
            if persisted.started_phase is None
            else persisted.started_phase.value,
            "expiration": cast(JsonValue, persisted.expiration.to_payload()),
        }
        identity: dict[str, JsonValue] = {
            "source_template": template,
            "duration": duration,
            "selected_source": {
                key: value for key, value in raw.items() if key != "source_instance_id"
            },
        }
        normalized = {
            **raw,
            "source_instance_id": "own-model-weapon-grant:"
            + sha256(canonical_json(identity).encode()).hexdigest(),
        }
        prefix = "selected-weapon-source:"
        replacements[prefix + canonical_json(raw)] = prefix + canonical_json(normalized)
    return replacements
