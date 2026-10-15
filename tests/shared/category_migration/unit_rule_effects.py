from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_rule_effects import (
    charge_transit_through_non_vehicle_monster_models_allowed,
    embark_transport_forbidden_by_effects,
    embark_transport_forbidden_effect_source_ids,
    fire_overwatch_forbidden_by_effects,
    movement_bonus_inches_from_effects,
    movement_model_transit_permissions_from_effects,
    movement_transit_through_terrain_features_allowed,
)


def _effect(
    effect_id: str,
    *,
    payload: JsonValue,
    owner_player_id: str = "player-a",
    source_rule_id: str = "source-rule",
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=f"effect:{effect_id}",
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=("unit-a",),
        started_battle_round=1,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            player_id=owner_player_id,
        ),
        effect_payload=payload,
    )


def _generic_rule_effect(
    effect_id: str,
    *,
    owner_player_id: str = "player-a",
    effect_kind: str = "movement_transit_permission",
    parameters: tuple[tuple[str, JsonValue], ...],
) -> PersistingEffect:
    return _effect(
        effect_id,
        owner_player_id=owner_player_id,
        payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": {
                "kind": effect_kind,
                "parameters": [{"key": key, "value": value} for key, value in parameters],
            },
        },
    )


__all__: list[str] = []
__all__ += ["GENERIC_RULE_EFFECT_KIND", "BattlePhase", "EffectExpiration", "GameLifecycleError"]
__all__ += ["JsonValue", "PersistingEffect", "_effect", "_generic_rule_effect", "cast"]
__all__ += ["charge_transit_through_non_vehicle_monster_models_allowed"]
__all__ += ["embark_transport_forbidden_by_effects"]
__all__ += ["embark_transport_forbidden_effect_source_ids", "fire_overwatch_forbidden_by_effects"]
__all__ += ["movement_bonus_inches_from_effects"]
__all__ += ["movement_model_transit_permissions_from_effects"]
__all__ += ["movement_transit_through_terrain_features_allowed", "pytest"]
