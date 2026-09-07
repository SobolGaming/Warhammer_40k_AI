from __future__ import annotations

from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase


def generic_effect(
    *,
    effect_id: str,
    owner_player_id: str,
    target_unit_instance_ids: tuple[str, ...],
    target_kind: str,
    effect_kind: str,
    parameters: dict[str, JsonValue],
    conditions: tuple[dict[str, JsonValue], ...] = (),
    source_model_instance_id: str | None = None,
    trigger_payload: dict[str, JsonValue] | None = None,
) -> PersistingEffect:
    parameter_payloads: list[dict[str, JsonValue]] = [
        {"key": key, "value": value} for key, value in sorted(parameters.items())
    ]
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=f"source:{effect_id}",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "rule_id": f"rule:{effect_id}",
                "source_id": f"source:{effect_id}",
                "rule_ir_hash": "0" * 64,
                "clause_id": f"clause:{effect_id}",
                "effect_index": 0,
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "target": {
                    "kind": target_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": [],
                },
                "target_unit_instance_ids": list(target_unit_instance_ids),
                "duration": None,
                "conditions": list(conditions),
                "effect": {
                    "kind": effect_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": parameter_payloads,
                },
                "context": {
                    "state": None,
                    "player_id": owner_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "source_model_instance_id": source_model_instance_id,
                    "trigger_payload": trigger_payload,
                },
            }
        ),
    )
