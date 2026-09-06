"""Apply each source-backed Aura once per target, preserving physical evidence."""

from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_index_from_payload,
)
from warhammer40k_core.engine.phase import GameLifecycleError

_identifier = IdentifierValidator(GameLifecycleError)


def non_stacking_aura_applications(
    applications: tuple[tuple[str, PersistingEffect], ...],
) -> tuple[tuple[str, PersistingEffect], ...]:
    """Select deterministic representatives for one queried rules unit.

    Clause/effect slots preserve every sub-effect of an ability. Physical model,
    component and effect instance IDs never create additional Aura applications.
    Non-Aura effects retain their own stacking and lifetime policies.
    """
    selected: list[tuple[str, PersistingEffect]] = []
    seen: dict[tuple[str, str, int], dict[str, JsonValue]] = {}
    for target_id, effect in applications:
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            selected.append((target_id, effect))
            continue
        target = payload.get("target")
        if not isinstance(target, dict) or target.get("kind") != "aura_units":
            selected.append((target_id, effect))
            continue
        key = (
            _identifier("Aura source_id", payload.get("source_id")),
            _identifier("Aura clause_id", payload.get("clause_id")),
            generic_rule_effect_index_from_payload(payload),
        )
        if any(
            field not in payload for field in ("rule_ir_hash", "effect", "conditions", "target")
        ):
            raise GameLifecycleError("Aura application is missing its source semantics.")
        semantics = {
            field: payload[field] for field in ("rule_ir_hash", "effect", "conditions", "target")
        }
        if key in seen:
            if seen[key] != semantics:
                raise GameLifecycleError(
                    "The same Aura application has conflicting source semantics."
                )
            continue
        seen[key] = semantics
        selected.append((target_id, effect))
    return tuple(selected)


def persisting_effects_for_target(
    effects: list[PersistingEffect], unit_instance_id: str
) -> tuple[PersistingEffect, ...]:
    target_id = _identifier("unit_instance_id", unit_instance_id)
    return tuple(
        effect
        for _, effect in non_stacking_aura_applications(
            tuple((target_id, effect) for effect in effects if effect.applies_to_unit(target_id))
        )
    )
