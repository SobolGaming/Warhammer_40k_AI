"""Compare actual Cover grants while retaining each observer's causal witness."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.core_stratagem_effects import unit_effects_grant_benefit_of_cover
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_inventories
from warhammer40k_core.engine.shooting_targets import BENEFIT_OF_COVER_RULE_ID
from warhammer40k_core.engine.stealth import rules_unit_stealth_sources

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def cover_gathering_inventories(
    *, state: GameState, pool: RangedAttackPool, registry: RuntimeModifierRegistry
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    raw, applicable = obscuring_model_cover_inventories(state=state, pool=pool)
    common = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "effects": [
                    effect.to_payload()
                    for effect in state.persisting_effects_for_unit(pool.target_unit_instance_id)
                    if unit_effects_grant_benefit_of_cover((effect,))
                ],
                "stealth": rules_unit_stealth_sources(
                    state=state,
                    target_unit_instance_id=pool.target_unit_instance_id,
                    runtime_modifier_registry=registry,
                ),
            }
        ),
    )
    return {**common, "obscuring_models": raw}, {**common, "obscuring_models": applicable}


def compare_cover_modifier(
    rules: dict[str, JsonValue], *, raw: dict[str, JsonValue], applicable: dict[str, JsonValue]
) -> None:
    """Normalize only the exact Cover ID generated from this current owner inventory."""
    expected = BENEFIT_OF_COVER_RULE_ID + ":" + sha256(canonical_json(raw).encode()).hexdigest()
    replacement = (
        BENEFIT_OF_COVER_RULE_ID + ":" + sha256(canonical_json(applicable).encode()).hexdigest()
    )
    for item in cast(list[dict[str, JsonValue]], rules["hit_modifiers"]):
        modifier = cast(dict[str, JsonValue], item["modifier"])
        if (
            item["kind"] == "skill"
            and modifier["source_id"] == BENEFIT_OF_COVER_RULE_ID
            and modifier["modifier_id"] == expected
        ):
            modifier["modifier_id"] = replacement
