from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_disembark_state import (
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


ASSAULT_DISEMBARK_PERMISSION_EFFECT_KIND = "assault_disembark_permission"
_PERMISSION_PAYLOAD_KEYS = frozenset(
    (
        "effect_kind",
        "eligible_rules_unit_instance_ids",
        "transport_unit_instance_id",
    )
)


def assault_disembark_permission_effect(
    *,
    effect_id: str,
    source_rule_id: str,
    owner_player_id: str,
    transport_unit_instance_id: str,
    eligible_rules_unit_instance_ids: tuple[str, ...],
    started_battle_round: int,
    expiration: EffectExpiration,
    started_phase: BattlePhaseKind | None = None,
) -> PersistingEffect:
    transport_id = _validate_identifier(
        "transport_unit_instance_id",
        transport_unit_instance_id,
    )
    eligible_ids = _validate_identifier_tuple(
        "eligible_rules_unit_instance_ids",
        eligible_rules_unit_instance_ids,
    )
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(transport_id,),
        started_battle_round=started_battle_round,
        started_phase=started_phase,
        expiration=expiration,
        effect_payload={
            "effect_kind": ASSAULT_DISEMBARK_PERMISSION_EFFECT_KIND,
            "transport_unit_instance_id": transport_id,
            "eligible_rules_unit_instance_ids": list(eligible_ids),
        },
    )


def assault_disembark_restriction_overrides(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    rules_unit_instance_id: str,
    transport_unit_instance_id: str,
) -> tuple[TransportRestrictionOverride, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    transport_id = _validate_identifier(
        "transport_unit_instance_id",
        transport_unit_instance_id,
    )
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("battle_round must be a positive integer.")
    source_rule_ids: list[str] = []
    for effect in state.persisting_effects_for_unit(transport_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != (
            ASSAULT_DISEMBARK_PERMISSION_EFFECT_KIND
        ):
            continue
        eligible_ids = _assault_disembark_eligible_ids(
            effect=effect,
            payload=payload,
            player_id=requested_player_id,
            battle_round=battle_round,
            transport_unit_instance_id=transport_id,
        )
        if requested_unit_id in eligible_ids:
            source_rule_ids.append(effect.source_rule_id)
    if len(source_rule_ids) > 1:
        raise GameLifecycleError(
            "Assault Disembark eligibility must have one unambiguous permitting source."
        )
    if not source_rule_ids:
        return ()
    return (
        TransportRestrictionOverride(
            override_kind=(
                TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK_AFTER_NORMAL_MOVE
            ),
            source_rule_id=source_rule_ids[0],
        ),
    )


def _assault_disembark_eligible_ids(
    *,
    effect: PersistingEffect,
    payload: dict[str, JsonValue],
    player_id: str,
    battle_round: int,
    transport_unit_instance_id: str,
) -> tuple[str, ...]:
    if set(payload).symmetric_difference(_PERMISSION_PAYLOAD_KEYS):
        raise GameLifecycleError("Assault Disembark permission payload fields are invalid.")
    payload_transport_id = _validate_identifier(
        "Assault Disembark permission transport_unit_instance_id",
        payload["transport_unit_instance_id"],
    )
    if payload_transport_id != transport_unit_instance_id or effect.target_unit_instance_ids != (
        transport_unit_instance_id,
    ):
        raise GameLifecycleError("Assault Disembark permission Transport identity drift.")
    if effect.owner_player_id != player_id:
        raise GameLifecycleError("Assault Disembark permission player identity drift.")
    if effect.started_battle_round > battle_round:
        raise GameLifecycleError("Assault Disembark permission starts in a future battle round.")
    raw_eligible_ids = payload["eligible_rules_unit_instance_ids"]
    if not isinstance(raw_eligible_ids, list):
        raise GameLifecycleError(
            "Assault Disembark eligible_rules_unit_instance_ids must be a list."
        )
    return _validate_identifier_tuple(
        "Assault Disembark eligible_rules_unit_instance_ids",
        tuple(cast(list[object], raw_eligible_ids)),
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if not validated:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(validated) != len(set(validated)):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


__all__ = (
    "ASSAULT_DISEMBARK_PERMISSION_EFFECT_KIND",
    "assault_disembark_permission_effect",
    "assault_disembark_restriction_overrides",
)
