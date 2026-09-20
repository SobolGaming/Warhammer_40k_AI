"""Turn-long Firing Deck restrictions use the shared persistent-effect authority."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import msgspec

from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_firing_deck_2026_09 import (
    FIRING_DECK_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

FIRING_DECK_RESTRICTION_KIND = "firing_deck_shooting_restriction"


class FiringDeckRestrictionPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    effect_kind: Literal["firing_deck_shooting_restriction"]
    transport_unit_instance_id: str
    result_id: str
    embarked_unit_instance_ids: tuple[str, ...]


def firing_deck_restriction_payload(
    effect: PersistingEffect,
) -> FiringDeckRestrictionPayload | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != FIRING_DECK_RESTRICTION_KIND:
        if effect.source_rule_id == FIRING_DECK_SOURCE_ID:
            raise GameLifecycleError("Firing Deck restriction payload is missing.")
        return None
    try:
        row = msgspec.convert(payload, type=FiringDeckRestrictionPayload)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("Firing Deck restriction payload is invalid.") from exc
    identifiers = (row.transport_unit_instance_id, row.result_id, *row.embarked_unit_instance_ids)
    if (
        any(not value or value != value.strip() for value in identifiers)
        or not row.embarked_unit_instance_ids
        or row.embarked_unit_instance_ids != tuple(sorted(set(row.embarked_unit_instance_ids)))
        or row.embarked_unit_instance_ids != effect.target_unit_instance_ids
        or row.transport_unit_instance_id in effect.target_unit_instance_ids
        or effect.source_rule_id != FIRING_DECK_SOURCE_ID
        or effect.effect_id != f"firing-deck:{row.result_id}"
        or effect.started_phase is not BattlePhase.SHOOTING
        or effect.expiration
        != EffectExpiration.end_turn(
            battle_round=effect.started_battle_round, player_id=effect.owner_player_id
        )
    ):
        raise GameLifecycleError("Firing Deck restriction source, snapshot or timing drifted.")
    return row


def build_firing_deck_restriction(
    *,
    player_id: str,
    battle_round: int,
    transport_unit_instance_id: str,
    embarked_unit_instance_ids: tuple[str, ...],
    result_id: str,
) -> PersistingEffect:
    effect = PersistingEffect(
        effect_id=f"firing-deck:{result_id}",
        source_rule_id=FIRING_DECK_SOURCE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=embarked_unit_instance_ids,
        started_battle_round=battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_turn(battle_round=battle_round, player_id=player_id),
        effect_payload=validate_json_value(
            msgspec.to_builtins(
                FiringDeckRestrictionPayload(
                    effect_kind="firing_deck_shooting_restriction",
                    transport_unit_instance_id=transport_unit_instance_id,
                    result_id=result_id,
                    embarked_unit_instance_ids=embarked_unit_instance_ids,
                )
            )
        ),
    )
    firing_deck_restriction_payload(effect)
    return effect


def record_firing_deck_restriction(
    *,
    state: GameState,
    transport_unit_instance_id: str,
    embarked_unit_instance_ids: tuple[str, ...],
    result_id: str,
) -> None:
    if not embarked_unit_instance_ids:
        return
    if state.active_player_id is None or state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Firing Deck requires the owner's Shooting phase.")
    state.record_persisting_effect(
        build_firing_deck_restriction(
            player_id=state.active_player_id,
            battle_round=state.battle_round,
            transport_unit_instance_id=transport_unit_instance_id,
            embarked_unit_instance_ids=embarked_unit_instance_ids,
            result_id=result_id,
        )
    )


def firing_deck_prevents_shooting(*, state: GameState, rules_unit: RulesUnitView) -> bool:
    identities = {rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids}
    for effect in state.persisting_effects:
        if not identities.intersection(effect.target_unit_instance_ids):
            continue
        if firing_deck_restriction_payload(effect) is None:
            continue
        if effect.owner_player_id != rules_unit.owner_player_id:
            raise GameLifecycleError("Firing Deck restriction ownership drifted.")
        if (
            effect.started_battle_round == state.battle_round
            and effect.owner_player_id == state.active_player_id
        ):
            return True
    return False
