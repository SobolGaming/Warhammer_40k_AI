"""Canonical shared session fixture for general source-backed modifier choices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.psychic_modifier_helpers import pending_request, psychic_session, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase


def modifier_session(
    phase: BattlePhase = BattlePhase.SHOOTING,
    *,
    weapon_profile_transform: Callable[[WeaponProfile], WeaponProfile] | None = None,
) -> LocalGameSession:
    session = psychic_session(
        phase, psychic=False, weapon_profile_transform=weapon_profile_transform
    )
    state = session.lifecycle.state
    assert state is not None
    for owner, unit_id in (
        ("player-a", "army-alpha:intercessor-1"),
        ("player-b", "army-beta:enemy"),
    ):
        effect = generic_effect(
            effect_id=f"ignore:{owner}",
            owner_player_id=owner,
            target_unit_instance_ids=(unit_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                effect_payload={**payload, "context": {**context, "phase": phase.value}},
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=phase, player_id="player-a"
                ),
            )
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))


def reach_modifier_request(session: LocalGameSession) -> DecisionRequest:
    for _ in range(35):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            return request
        submit_fixture_request(session, request)
    raise AssertionError("Did not reach a generic modifier choice.")
